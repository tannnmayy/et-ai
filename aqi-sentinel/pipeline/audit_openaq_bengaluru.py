from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.openaq_client import OpenAQClient, OpenAQConfig, OpenAQLocation, OpenAQSensor, normalize_parameter_name, utc_run_timestamp
from pipeline.storage import ensure_parent, write_parquet

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OPENAQ_DIR = PROJECT_ROOT / "data" / "raw" / "openaq"
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
PROCESSED_OPENAQ_HOURLY = PROJECT_ROOT / "data" / "processed" / "bengaluru_openaq_station_hourly.parquet"
AUDIT_CSV = REPORTS_DIR / "openaq_bengaluru_station_audit.csv"
AUDIT_MD = REPORTS_DIR / "openaq_bengaluru_station_audit.md"
LOCATIONS_CSV = REPORTS_DIR / "openaq_bengaluru_locations.csv"
SENSORS_CSV = REPORTS_DIR / "openaq_bengaluru_sensors.csv"
POLLUTANTS = {"pm25", "pm10", "no2"}
COMPATIBLE_UNITS = {"ug/m3", "ug/m^3", "µg/m³", "micrograms/m3", "micrograms per cubic meter"}


@dataclass(frozen=True)
class BoundingBox:
    south: float = 12.80
    north: float = 13.15
    west: float = 77.40
    east: float = 77.85

    def openaq_bbox(self) -> str:
        return f"{self.west:.4f},{self.south:.4f},{self.east:.4f},{self.north:.4f}"


def normalize_hourly_measurements(
    measurements: list[dict[str, Any]],
    sensor: OpenAQSensor,
    location: OpenAQLocation,
) -> pd.DataFrame:
    """Normalize OpenAQ hourly records into long-form station measurements."""
    records: list[dict[str, Any]] = []
    logged_incompatible = False
    for item in measurements:
        parameter = normalize_parameter_name(_extract_parameter_name(item, sensor))
        if parameter not in POLLUTANTS:
            continue
        units = _extract_units(item, sensor)
        if not _is_compatible_unit(units):
            if not logged_incompatible:
                logger.warning("Skipping sensor %s records with incompatible units: %s", sensor.sensor_id, units)
                logged_incompatible = True
            continue
        if item.get("value") is None:
            continue
        value = float(item["value"])
        if value < 0:
            continue
        timestamp = _extract_timestamp(item)
        coordinates = item.get("coordinates") or {}
        records.append(
            {
                "timestamp_utc": timestamp,
                "location_id": location.location_id,
                "location_name": location.name,
                "station_id": f"openaq_location_{location.location_id}",
                "station_name": location.name,
                "sensor_id": sensor.sensor_id,
                "parameter": parameter,
                "value": value,
                "units": units,
                "latitude": _coalesce_float(coordinates.get("latitude"), location.latitude),
                "longitude": _coalesce_float(coordinates.get("longitude"), location.longitude),
                "source": "openaq_v3",
                "is_unusually_high": value > _high_value_threshold(parameter),
            }
        )
    return pd.DataFrame.from_records(records)


def aggregate_hourly_long_form(long_form: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if long_form.empty:
        return long_form.copy(), 0
    frame = long_form.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True).dt.floor("h")
    duplicate_count = int(frame.duplicated(["station_id", "parameter", "timestamp_utc"]).sum())
    grouped = (
        frame.groupby(
            [
                "timestamp_utc",
                "location_id",
                "location_name",
                "station_id",
                "station_name",
                "parameter",
                "units",
                "latitude",
                "longitude",
                "source",
            ],
            dropna=False,
            as_index=False,
        )["value"]
        .median()
    )
    return grouped, duplicate_count


def build_station_hourly_wide(hourly_long: pd.DataFrame) -> pd.DataFrame:
    columns = ["timestamp_utc", "station_id", "station_name", "latitude", "longitude", "pm25", "pm10", "no2"]
    if hourly_long.empty:
        return pd.DataFrame(columns=columns)
    pivot = hourly_long.pivot_table(
        index=["timestamp_utc", "station_id", "station_name", "latitude", "longitude"],
        columns="parameter",
        values="value",
        aggfunc="median",
    ).reset_index()
    pivot.columns.name = None
    for column in ["pm25", "pm10", "no2"]:
        if column not in pivot.columns:
            pivot[column] = pd.NA
    pivot = pivot[columns].sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)
    complete_station_frames: list[pd.DataFrame] = []
    for _, station in pivot.groupby("station_id"):
        station = station.sort_values("timestamp_utc")
        full_index = pd.date_range(station["timestamp_utc"].min(), station["timestamp_utc"].max(), freq="h")
        full = station.set_index("timestamp_utc").reindex(full_index).rename_axis("timestamp_utc").reset_index()
        for metadata_column in ["station_id", "station_name", "latitude", "longitude"]:
            full[metadata_column] = full[metadata_column].ffill().bfill()
        complete_station_frames.append(full[columns])
    return pd.concat(complete_station_frames, ignore_index=True).sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)


def calculate_station_quality_metrics(wide: pd.DataFrame, duplicate_counts: dict[str, int] | None = None) -> pd.DataFrame:
    duplicate_counts = duplicate_counts or {}
    rows: list[dict[str, Any]] = []
    if wide.empty:
        return pd.DataFrame(columns=_audit_columns())

    frame = wide.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    for station_id, group in frame.groupby("station_id"):
        group = group.sort_values("timestamp_utc")
        earliest = group["timestamp_utc"].min()
        latest = group["timestamp_utc"].max()
        expected_hours = int(((latest - earliest).total_seconds() // 3600) + 1) if pd.notna(earliest) and pd.notna(latest) else 0
        covered_days = round(expected_hours / 24, 2) if expected_hours else 0.0
        pm25_hours = int(group["pm25"].notna().sum())
        pm10_hours = int(group["pm10"].notna().sum())
        no2_hours = int(group["no2"].notna().sum())
        longest_run = longest_continuous_run_hours(group[["timestamp_utc", "pm25"]])
        gaps_over_24h = count_pm25_gaps_over_24h(group[["timestamp_utc", "pm25"]])
        pm25_completeness = _percent(pm25_hours, expected_hours)
        pm10_completeness = _percent(pm10_hours, expected_hours)
        no2_completeness = _percent(no2_hours, expected_hours)
        classification, reason = classify_station(covered_days, pm25_completeness, longest_run)
        first = group.iloc[0]
        available = [name for name in ["pm25", "pm10", "no2"] if int(group[name].notna().sum()) > 0]
        rows.append(
            {
                "station_id": station_id,
                "station_name": first["station_name"],
                "latitude": float(first["latitude"]) if pd.notna(first["latitude"]) else None,
                "longitude": float(first["longitude"]) if pd.notna(first["longitude"]) else None,
                "available_pollutants": ",".join(available),
                "earliest_timestamp_utc": earliest.isoformat(),
                "latest_timestamp_utc": latest.isoformat(),
                "covered_days": covered_days,
                "total_observed_hours": int(group[["pm25", "pm10", "no2"]].notna().any(axis=1).sum()),
                "expected_hours_in_covered_range": expected_hours,
                "pm25_observed_hours": pm25_hours,
                "pm10_observed_hours": pm10_hours,
                "no2_observed_hours": no2_hours,
                "pm25_completeness_percent": pm25_completeness,
                "pm10_completeness_percent": pm10_completeness,
                "no2_completeness_percent": no2_completeness,
                "pm25_missingness_percent": round(100.0 - pm25_completeness, 2),
                "duplicate_count_before_hourly_aggregation": duplicate_counts.get(station_id, 0),
                "longest_continuous_pm25_run_hours": longest_run,
                "longest_continuous_pm25_run_days": round(longest_run / 24, 2),
                "number_of_pm25_gaps_over_24h": gaps_over_24h,
                "quality_classification": classification,
                "recommendation_reason": reason,
            }
        )
    order = {"Recommended": 0, "Usable with caveats": 1, "Not suitable": 2}
    audit = pd.DataFrame(rows, columns=_audit_columns())
    audit["_sort_order"] = audit["quality_classification"].map(order)
    return audit.sort_values(["_sort_order", "station_id"]).drop(columns="_sort_order").reset_index(drop=True)


def longest_continuous_run_hours(station_frame: pd.DataFrame) -> int:
    if station_frame.empty:
        return 0
    frame = station_frame.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    observed = frame.loc[frame["pm25"].notna(), "timestamp_utc"].sort_values()
    if observed.empty:
        return 0
    longest = current = 1
    previous = observed.iloc[0]
    for timestamp in observed.iloc[1:]:
        if timestamp - previous == pd.Timedelta(hours=1):
            current += 1
        else:
            longest = max(longest, current)
            current = 1
        previous = timestamp
    return max(longest, current)


def count_pm25_gaps_over_24h(station_frame: pd.DataFrame) -> int:
    if station_frame.empty:
        return 0
    frame = station_frame.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    full = frame.set_index("timestamp_utc").sort_index().asfreq("h")
    missing = full["pm25"].isna()
    gaps = 0
    current = 0
    for is_missing in missing:
        if is_missing:
            current += 1
        else:
            if current > 24:
                gaps += 1
            current = 0
    if current > 24:
        gaps += 1
    return gaps


def classify_station(covered_days: float, pm25_completeness_percent: float, longest_run_hours: int) -> tuple[str, str]:
    if covered_days >= 180 and pm25_completeness_percent >= 70 and longest_run_hours >= 720:
        return "Recommended", "Passed Recommended rule: >=180 covered days, >=70% PM2.5 completeness, and >=30 continuous PM2.5 days."
    if covered_days >= 90 and pm25_completeness_percent >= 50 and longest_run_hours >= 168:
        return "Usable with caveats", "Passed Usable with caveats rule: >=90 covered days, >=50% PM2.5 completeness, and >=7 continuous PM2.5 days."
    failed = []
    if covered_days < 90:
        failed.append("covered_days < 90")
    if pm25_completeness_percent < 50:
        failed.append("PM2.5 completeness < 50%")
    if longest_run_hours < 168:
        failed.append("longest continuous PM2.5 run < 7 days")
    return "Not suitable", "Failed suitability rule: " + ", ".join(failed)


def generate_markdown_report(
    audit: pd.DataFrame,
    bbox: BoundingBox,
    lookback_days: int,
    locations_discovered: int,
    output_path: Path = AUDIT_MD,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    pm25_count = _count_with_pollutant(audit, "pm25")
    pm10_count = _count_with_pollutant(audit, "pm10")
    no2_count = _count_with_pollutant(audit, "no2")
    recommended = audit[audit["quality_classification"] == "Recommended"] if not audit.empty else audit
    caveats = audit[audit["quality_classification"] == "Usable with caveats"] if not audit.empty else audit
    not_suitable = audit[audit["quality_classification"] == "Not suitable"] if not audit.empty else audit

    lines = [
        "# OpenAQ Bengaluru Station Audit",
        "",
        f"Generated at: {generated_at}",
        "",
        f"Bounding box: south={bbox.south}, north={bbox.north}, west={bbox.west}, east={bbox.east}",
        f"Lookback period: {lookback_days} days",
        "",
        "Data-source disclaimer: OpenAQ aggregates public air-quality data and may not include all official monitoring data.",
        "OpenAQ coverage can be incomplete; validate results against official CPCB exports if necessary.",
        "This audit does not train or validate a forecasting model.",
        "",
        "## Summary",
        "",
        f"- Locations discovered: {locations_discovered}",
        f"- Locations with PM2.5: {pm25_count}",
        f"- Locations with PM10: {pm10_count}",
        f"- Locations with NO2: {no2_count}",
        f"- Recommended stations: {len(recommended)}",
        f"- Usable-with-caveats stations: {len(caveats)}",
        f"- Not-suitable stations: {len(not_suitable)}",
        "",
        "## Station Quality Table",
        "",
        _markdown_table(audit),
        "",
        "## Recommended stations for Milestone 2B",
        "",
    ]
    if recommended.empty:
        lines.append("No station meets the Recommended threshold.")
    else:
        for row in recommended.itertuples(index=False):
            lines.append(
                f"- {row.station_name} ({row.station_id}): PM2.5 completeness {row.pm25_completeness_percent}%, "
                f"longest run {row.longest_continuous_pm25_run_days} days."
            )
    lines.extend(
        [
            "",
            "## Known limitations",
            "",
            "- OpenAQ station coverage in Bengaluru may be incomplete.",
            "- Provider outages, sensor maintenance, and reporting gaps can affect completeness.",
            "- Unit compatibility is enforced; incompatible or unknown units are skipped rather than converted silently.",
            "- This phase audits data suitability only and does not retrain or validate the forecasting model.",
        ]
    )
    text = "\n".join(lines) + "\n"
    ensure_parent(output_path)
    output_path.write_text(text, encoding="utf-8")
    return text


def run_audit(lookback_days: int, refresh: bool = False, bbox: BoundingBox = BoundingBox()) -> pd.DataFrame:
    config = OpenAQConfig.from_env()
    client = OpenAQClient(config=config, raw_dir=RAW_OPENAQ_DIR)
    run_timestamp = utc_run_timestamp()
    datetime_to = datetime.now(timezone.utc).replace(microsecond=0)
    datetime_from = datetime_to - timedelta(days=lookback_days)

    locations = client.get_locations_for_bbox(bbox.openaq_bbox(), run_timestamp, refresh)
    location_by_id = {location.location_id: location for location in locations}
    _write_locations_table(locations, LOCATIONS_CSV)
    sensors: list[OpenAQSensor] = []
    for location in locations:
        sensors.extend(client.get_sensors_for_location(location.location_id, run_timestamp, refresh))
    _write_sensors_table(sensors, location_by_id, SENSORS_CSV)
    relevant_sensors = [
        sensor for sensor in sensors
        if sensor.parameter in POLLUTANTS and (sensor.units is None or _is_compatible_unit(sensor.units))
    ]

    long_frames: list[pd.DataFrame] = []
    for sensor in relevant_sensors:
        location = location_by_id[sensor.location_id]
        measurements = client.get_hourly_measurements(
            sensor.sensor_id,
            datetime_from.isoformat(),
            datetime_to.isoformat(),
            run_timestamp,
            refresh,
        )
        normalized = normalize_hourly_measurements(measurements, sensor, location)
        if not normalized.empty:
            long_frames.append(normalized)

    long_form = pd.concat(long_frames, ignore_index=True) if long_frames else pd.DataFrame()
    hourly_long, _ = aggregate_hourly_long_form(long_form)
    duplicate_counts = _duplicate_counts_by_station(long_form)
    wide = build_station_hourly_wide(hourly_long)
    write_parquet(wide, PROCESSED_OPENAQ_HOURLY)
    audit = calculate_station_quality_metrics(wide, duplicate_counts)
    ensure_parent(AUDIT_CSV)
    audit.to_csv(AUDIT_CSV, index=False)
    generate_markdown_report(audit, bbox, lookback_days, len(locations), AUDIT_MD)
    print_terminal_summary(audit, len(locations))
    logger.info("OpenAQ hourly station table written to %s", PROCESSED_OPENAQ_HOURLY)
    logger.info("OpenAQ audit reports written to %s and %s", AUDIT_CSV, AUDIT_MD)
    return audit


def print_terminal_summary(audit: pd.DataFrame, locations_discovered: int) -> None:
    recommended = audit[audit["quality_classification"] == "Recommended"] if not audit.empty else audit
    stations_with_pm25 = _count_with_pollutant(audit, "pm25")
    print("OpenAQ Bengaluru Audit Complete")
    print(f"Locations discovered: {locations_discovered}")
    print(f"Stations with PM2.5: {stations_with_pm25}")
    print(f"Recommended stations: {len(recommended)}")
    print("")
    if recommended.empty:
        print("No station meets the Recommended threshold.")
        print("Use the Usable with caveats list, expand the lookback period, or import official CPCB CSV data.")
    else:
        print("Recommended:")
        for row in recommended.itertuples(index=False):
            print(f"- {row.station_name} ({row.station_id}): PM2.5 completeness {row.pm25_completeness_percent}%, longest run {row.longest_continuous_pm25_run_days} days")
    print("")
    print("Next step:")
    print("Use recommended stations to request ERA5 weather for the exact historical date range.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit OpenAQ v3 station coverage for Bengaluru.")
    parser.add_argument("--lookback-days", type=int, default=365, help="Number of days of hourly OpenAQ history to inspect.")
    parser.add_argument("--refresh", action="store_true", help="Ignore cached raw OpenAQ payloads and fetch fresh responses.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    run_audit(lookback_days=args.lookback_days, refresh=args.refresh)


def _extract_parameter_name(item: dict[str, Any], sensor: OpenAQSensor) -> str:
    parameter = item.get("parameter")
    if isinstance(parameter, dict):
        return str(parameter.get("name") or parameter.get("displayName") or sensor.raw_parameter_name)
    return sensor.raw_parameter_name


def _extract_units(item: dict[str, Any], sensor: OpenAQSensor) -> str | None:
    parameter = item.get("parameter")
    if isinstance(parameter, dict):
        return parameter.get("units") or sensor.units
    return sensor.units


def _extract_timestamp(item: dict[str, Any]) -> pd.Timestamp:
    for key in ["period", "datetime", "date"]:
        value = item.get(key)
        if isinstance(value, dict):
            for nested_key in ["datetimeFrom", "from", "utc"]:
                nested = value.get(nested_key)
                if isinstance(nested, dict):
                    nested = nested.get("utc")
                if nested:
                    return _to_utc_timestamp(nested)
        elif value:
            return _to_utc_timestamp(value)
    datetime_from = item.get("datetimeFrom")
    if isinstance(datetime_from, dict) and datetime_from.get("utc"):
        return _to_utc_timestamp(datetime_from["utc"])
    raise ValueError("OpenAQ measurement record did not include a recognizable UTC timestamp.")


def _to_utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _is_compatible_unit(units: str | None) -> bool:
    if not units:
        return False
    normalized = units.lower().replace("μ", "µ").replace(" ", "")
    return normalized in {unit.lower().replace(" ", "") for unit in COMPATIBLE_UNITS}


def _high_value_threshold(parameter: str) -> float:
    return {"pm25": 500.0, "pm10": 700.0, "no2": 400.0}.get(parameter, 999999.0)


def _coalesce_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _percent(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def _count_with_pollutant(audit: pd.DataFrame, pollutant: str) -> int:
    if audit.empty or "available_pollutants" not in audit:
        return 0
    return int(audit["available_pollutants"].fillna("").str.split(",").apply(lambda values: pollutant in values).sum())


def _duplicate_counts_by_station(long_form: pd.DataFrame) -> dict[str, int]:
    if long_form.empty:
        return {}
    frame = long_form.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True).dt.floor("h")
    return frame.groupby("station_id").apply(lambda group: int(group.duplicated(["parameter", "timestamp_utc"]).sum())).to_dict()


def _write_locations_table(locations: list[OpenAQLocation], output_path: Path) -> None:
    rows = [
        {
            "location_id": location.location_id,
            "location_name": location.name,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "locality": location.locality,
            "country_code": location.country_code,
            "country_name": location.country_name,
            "is_active": location.is_active,
        }
        for location in locations
    ]
    ensure_parent(output_path)
    pd.DataFrame(rows).to_csv(output_path, index=False)


def _write_sensors_table(sensors: list[OpenAQSensor], locations: dict[int, OpenAQLocation], output_path: Path) -> None:
    rows = []
    for sensor in sensors:
        location = locations.get(sensor.location_id)
        rows.append(
            {
                "sensor_id": sensor.sensor_id,
                "location_id": sensor.location_id,
                "location_name": location.name if location else None,
                "parameter": sensor.parameter,
                "raw_parameter_name": sensor.raw_parameter_name,
                "units": sensor.units,
                "is_relevant_for_audit": sensor.parameter in POLLUTANTS,
            }
        )
    ensure_parent(output_path)
    pd.DataFrame(rows).to_csv(output_path, index=False)


def _markdown_table(audit: pd.DataFrame) -> str:
    if audit.empty:
        return "No station data available."
    columns = [
        "station_id",
        "station_name",
        "available_pollutants",
        "covered_days",
        "pm25_completeness_percent",
        "longest_continuous_pm25_run_days",
        "quality_classification",
    ]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in audit[columns].itertuples(index=False):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _audit_columns() -> list[str]:
    return [
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "available_pollutants",
        "earliest_timestamp_utc",
        "latest_timestamp_utc",
        "covered_days",
        "total_observed_hours",
        "expected_hours_in_covered_range",
        "pm25_observed_hours",
        "pm10_observed_hours",
        "no2_observed_hours",
        "pm25_completeness_percent",
        "pm10_completeness_percent",
        "no2_completeness_percent",
        "pm25_missingness_percent",
        "duplicate_count_before_hourly_aggregation",
        "longest_continuous_pm25_run_hours",
        "longest_continuous_pm25_run_days",
        "number_of_pm25_gaps_over_24h",
        "quality_classification",
        "recommendation_reason",
    ]


if __name__ == "__main__":
    main()
