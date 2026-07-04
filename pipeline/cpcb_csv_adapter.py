from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MISSING_MARKERS = {"", "NA", "N/A", "NONE", "NULL", "-", "--", "INVALID", "NAN", "NaN", "nan", "null", "None"}

CANONICAL_FIELDS = (
    "timestamp_utc",
    "station_id",
    "station_name",
    "latitude",
    "longitude",
    "pm25",
    "pm10",
    "no2",
    "temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "rainfall_mm",
)

NUMERIC_FIELDS = (
    "pm25",
    "pm10",
    "no2",
    "temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "rainfall_mm",
    "latitude",
    "longitude",
)

NON_NEGATIVE_FIELDS = ("pm25", "pm10", "no2", "wind_speed_mps", "rainfall_mm")

DEFAULT_PLAUSIBILITY_THRESHOLDS: dict[str, tuple[str, float]] = {
    "pm25": (">", 1000.0),
    "pm10": (">", 1500.0),
    "no2": (">", 1000.0),
    "relative_humidity": ("range", 0.0, 100.0),
    "temperature_c": ("range", -10.0, 60.0),
    "wind_speed_mps": (">", 60.0),
    "rainfall_mm": (">", 250.0),
}

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": (
        "timestamp",
        "date",
        "from date",
        "to date",
        "date & time",
        "datetime",
    ),
    "pm25": (
        "pm2.5",
        "pm2.5 (µg/m³)",
        "pm2.5 (ug/m3)",
        "pm2.5 (ug/m³)",
        "pm2.5 (µg/m3)",
    ),
    "pm10": (
        "pm10",
        "pm10 (µg/m³)",
        "pm10 (ug/m3)",
        "pm10 (ug/m³)",
        "pm10 (µg/m3)",
    ),
    "no2": (
        "no2",
        "no₂",
        "no2 (µg/m³)",
        "no2 (ug/m3)",
        "no2 (ug/m³)",
        "no2 (µg/m3)",
    ),
    "temperature_c": (
        "at",
        "at (degc)",
        "at (°c)",
        "ambient temperature",
        "temperature",
        "temp",
    ),
    "relative_humidity": (
        "rh",
        "rh (%)",
        "relative humidity",
        "humidity",
    ),
    "wind_speed_mps": (
        "ws",
        "ws (m/s)",
        "wind speed",
    ),
    "rainfall_mm": (
        "rf",
        "rf (mm)",
        "rainfall",
        "precipitation",
    ),
    "station_id": ("station id", "station_id"),
    "station_name": ("station name", "station_name"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "long"),
}


@dataclass(frozen=True)
class CPCBStationConfig:
    station_id: str
    station_name: str
    source: str = "CPCB/KSPCB 15-minute station export"
    latitude: float | None = None
    longitude: float | None = None
    source_timezone: str = "Asia/Kolkata"


@dataclass
class CPCBQualityStats:
    raw_path: str = ""
    raw_headers: list[str] = field(default_factory=list)
    raw_row_count: int = 0
    cleaned_15min_row_count: int = 0
    invalid_timestamp_count: int = 0
    duplicate_timestamp_count: int = 0
    numeric_conversion_failures: dict[str, int] = field(default_factory=dict)
    negative_value_rejections: dict[str, int] = field(default_factory=dict)
    plausibility_flag_counts: dict[str, int] = field(default_factory=dict)
    timestamp_interpretation: str = ""
    source_timezone_assumption: str = ""
    utc_conversion_note: str = ""
    rainfall_treatment: str = ""
    earliest_timestamp_utc: str | None = None
    latest_timestamp_utc: str | None = None


def normalize_header(value: str) -> str:
    text = str(value).strip().lower()
    text = text.replace("µ", "u").replace("³", "3").replace("°", "deg").replace("₂", "2")
    text = re.sub(r"\s+", " ", text)
    return text


def build_header_mapping(headers: list[str]) -> dict[str, str]:
    normalized = {header: normalize_header(header) for header in headers}
    reverse_lookup = {normalize_header(alias): canonical for canonical, aliases in COLUMN_ALIASES.items() for alias in aliases}
    mapping: dict[str, str] = {}
    for original, normalized_header in normalized.items():
        if normalized_header in reverse_lookup:
            mapping[original] = reverse_lookup[normalized_header]
    return mapping


def read_raw_csv(path: str | Any) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def normalize_missing_values(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    for column in cleaned.columns:
        cleaned[column] = cleaned[column].astype(str).str.strip()
        cleaned.loc[cleaned[column].isin(MISSING_MARKERS), column] = pd.NA
    return cleaned


def map_source_columns(frame: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    renamed = frame.rename(columns=mapping)
    if "timestamp" in renamed.columns and "timestamp_utc" not in renamed.columns:
        renamed["timestamp_utc"] = renamed["timestamp"]
    canonical = pd.DataFrame(index=frame.index)
    for column in CANONICAL_FIELDS:
        if column in renamed.columns:
            canonical[column] = renamed[column]
        else:
            canonical[column] = pd.NA
    return canonical


def parse_timestamps(
    frame: pd.DataFrame,
    source_timezone: str,
) -> tuple[pd.Series, int, str, str]:
    raw_timestamps = frame["timestamp_utc"].astype(str).str.strip()
    parsed_local = pd.to_datetime(raw_timestamps, errors="coerce")
    invalid_count = int(parsed_local.isna().sum())
    localized = parsed_local.dt.tz_localize(source_timezone, ambiguous="NaT", nonexistent="NaT")
    timestamp_utc = localized.dt.tz_convert("UTC")
    interpretation = (
        "Raw timestamps are timezone-naive station readings. "
        f"They are localized to {source_timezone} and converted to UTC."
    )
    conversion_note = (
        f"Naive timestamps -> localize({source_timezone}) -> tz_convert(UTC). "
        "Invalid or ambiguous local timestamps are set to null."
    )
    return timestamp_utc, invalid_count, interpretation, conversion_note


def convert_numeric_field(series: pd.Series) -> tuple[pd.Series, int]:
    converted = pd.to_numeric(series, errors="coerce")
    failures = int(series.notna().sum() - converted.notna().sum())
    return converted, failures


def apply_negative_rejection(series: pd.Series) -> tuple[pd.Series, int]:
    rejected = int((series < 0).sum())
    cleaned = series.where(series >= 0)
    return cleaned, rejected


def flag_plausibility(frame: pd.DataFrame, thresholds: dict[str, Any] | None = None) -> tuple[pd.Series, dict[str, int]]:
    thresholds = thresholds or DEFAULT_PLAUSIBILITY_THRESHOLDS
    flagged = pd.Series(False, index=frame.index)
    counts: dict[str, int] = {}
    for column, rule in thresholds.items():
        if column not in frame.columns:
            continue
        values = frame[column]
        if rule[0] == ">":
            mask = values > rule[1]
        elif rule[0] == "range":
            mask = (values < rule[1]) | (values > rule[2])
        else:
            continue
        counts[column] = int(mask.fillna(False).sum())
        flagged = flagged | mask.fillna(False)
    return flagged, counts


def resolve_duplicate_timestamps(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    duplicate_count = int(frame.duplicated(["station_id", "timestamp_utc"]).sum())
    if duplicate_count == 0:
        return frame.sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True), 0

    aggregations: dict[str, str | type] = {column: "first" for column in frame.columns if column not in NUMERIC_FIELDS}
    for column in NUMERIC_FIELDS:
        if column in frame.columns:
            aggregations[column] = "median"
    aggregated = (
        frame.groupby(["station_id", "timestamp_utc"], as_index=False)
        .agg(aggregations)
        .sort_values(["station_id", "timestamp_utc"])
        .reset_index(drop=True)
    )
    return aggregated, duplicate_count


def detect_rainfall_mode(frame: pd.DataFrame) -> str:
    rainfall = frame["rainfall_mm"]
    if rainfall.notna().sum() == 0:
        return "Rainfall column is entirely missing; hourly rainfall remains null."
    diffs = rainfall.diff()
    non_decreasing = float((diffs.fillna(0) >= 0).mean())
    if non_decreasing > 0.95 and rainfall.max(skipna=True) > 5:
        return (
            "RF appears cumulative (mostly non-decreasing). Interval rainfall is derived as "
            "positive hour-over-hour differences with negative diffs treated as reset/null."
        )
    return "RF appears to represent interval rainfall; hourly rainfall uses sum of valid 15-minute RF values."


def derive_interval_rainfall(frame: pd.DataFrame) -> pd.Series:
    rainfall = frame["rainfall_mm"].astype(float)
    if rainfall.notna().sum() == 0:
        return rainfall
    diffs = rainfall.diff()
    if float((diffs.fillna(0) >= 0).mean()) > 0.95 and rainfall.max(skipna=True) > 5:
        interval = diffs.where(diffs >= 0)
        interval.iloc[0] = rainfall.iloc[0]
        return interval
    return rainfall


def clean_cpcb_frame(
    raw_frame: pd.DataFrame,
    station: CPCBStationConfig,
    raw_path: str | None = None,
) -> tuple[pd.DataFrame, CPCBQualityStats]:
    stats = CPCBQualityStats(
        raw_path=str(raw_path or ""),
        raw_headers=list(raw_frame.columns),
        raw_row_count=int(len(raw_frame)),
        source_timezone_assumption=station.source_timezone,
    )
    normalized = normalize_missing_values(raw_frame)
    mapping = build_header_mapping(list(normalized.columns))
    canonical = map_source_columns(normalized, mapping)

    timestamp_utc, invalid_count, interpretation, conversion_note = parse_timestamps(
        canonical,
        station.source_timezone,
    )
    stats.invalid_timestamp_count = invalid_count
    stats.timestamp_interpretation = interpretation
    stats.utc_conversion_note = conversion_note

    cleaned = canonical.copy()
    cleaned["source_timestamp"] = canonical["timestamp_utc"]
    cleaned["source_timezone"] = station.source_timezone
    cleaned["timestamp_utc"] = timestamp_utc
    cleaned["station_id"] = station.station_id
    cleaned["station_name"] = station.station_name
    cleaned["latitude"] = station.latitude
    cleaned["longitude"] = station.longitude
    cleaned["source"] = station.source

    if "station_id" in mapping.values() and canonical["station_id"].notna().any():
        cleaned["station_id"] = canonical["station_id"].fillna(station.station_id)
    if "station_name" in mapping.values() and canonical["station_name"].notna().any():
        cleaned["station_name"] = canonical["station_name"].fillna(station.station_name)

    for column in NUMERIC_FIELDS:
        if column not in cleaned.columns:
            continue
        converted, failures = convert_numeric_field(cleaned[column])
        stats.numeric_conversion_failures[column] = failures
        cleaned[column] = converted

    for column in NON_NEGATIVE_FIELDS:
        if column not in cleaned.columns:
            continue
        cleaned[column], rejected = apply_negative_rejection(cleaned[column])
        if rejected:
            stats.negative_value_rejections[column] = rejected

    cleaned["rainfall_mm"] = derive_interval_rainfall(cleaned)
    stats.rainfall_treatment = detect_rainfall_mode(cleaned)

    flagged, plausibility_counts = flag_plausibility(cleaned)
    cleaned["is_plausibility_flagged"] = flagged
    stats.plausibility_flag_counts = plausibility_counts

    cleaned = cleaned.dropna(subset=["timestamp_utc"]).copy()
    cleaned, duplicate_count = resolve_duplicate_timestamps(cleaned)
    stats.duplicate_timestamp_count = duplicate_count
    stats.cleaned_15min_row_count = int(len(cleaned))

    if not cleaned.empty:
        stats.earliest_timestamp_utc = pd.Timestamp(cleaned["timestamp_utc"].min()).isoformat()
        stats.latest_timestamp_utc = pd.Timestamp(cleaned["timestamp_utc"].max()).isoformat()

    return cleaned, stats


def load_and_clean_cpcb_csv(path: str | Any, station: CPCBStationConfig) -> tuple[pd.DataFrame, CPCBQualityStats]:
    raw = read_raw_csv(path)
    return clean_cpcb_frame(raw, station, raw_path=str(path))
