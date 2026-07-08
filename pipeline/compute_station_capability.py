from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("compute_station_capability")

POLLUTANT_KEYS = ("pm25", "pm10", "no2")
MISSINGNESS_THRESHOLD = 50.0


def _get_project_root() -> Path:
    try:
        from backend.app.config import get_project_root as _root
        return _root()
    except ImportError:
        return Path(__file__).resolve().parents[1]


def _load_quality_summary(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def compute_available_pollutants(quality: dict) -> list[str]:
    missingness = quality.get("missingness_hourly_percent", {})
    available = []
    for key in POLLUTANT_KEYS:
        pct = missingness.get(key)
        if pct is not None and pct <= MISSINGNESS_THRESHOLD:
            available.append(key)
    return available


def compute_pm25_coverage_status(quality: dict) -> str:
    missingness = quality.get("missingness_hourly_percent", {})
    pm25_pct = missingness.get("pm25")
    if pm25_pct is None:
        return "insufficient_pm25_history"
    if pm25_pct >= 100.0:
        return "pm25_sensor_unavailable"
    if pm25_pct > MISSINGNESS_THRESHOLD:
        return "insufficient_pm25_history"
    return "complete"


def compute_forecast_eligible(station_id: str, project_root: Path) -> bool:
    features_path = (
        project_root
        / "data"
        / "processed"
        / "real"
        / station_id
        / f"{station_id}_features_24h.parquet"
    )
    return features_path.exists()


def compute_station_capabilities(project_root: Path) -> list[dict]:
    registry_path = project_root / "data" / "reference" / "bengaluru_station_registry.csv"
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry not found: {registry_path}")

    with registry_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    results = []
    for row in rows:
        station_id = row.get("station_id", "").strip()
        if not station_id:
            continue

        quality_path = (
            project_root
            / "data"
            / "processed"
            / "real"
            / station_id
            / f"{station_id}_quality_summary.json"
        )

        if quality_path.exists():
            quality = _load_quality_summary(quality_path)
        else:
            logger.warning("Quality summary not found for %s at %s", station_id, quality_path)
            quality = {}

        available_pollutants = compute_available_pollutants(quality)
        pm25_status = compute_pm25_coverage_status(quality)
        disk_eligible = compute_forecast_eligible(station_id, project_root)

        if pm25_status == "complete" and not disk_eligible:
            logger.warning(
                "Station %s: pm25_forecast_coverage_status='complete' from quality data "
                "but _features_24h.parquet not found on disk. Setting forecast_eligible=False.",
                station_id,
            )
        if pm25_status != "complete" and disk_eligible:
            logger.warning(
                "Station %s: pm25_forecast_coverage_status='%s' from quality data "
                "but _features_24h.parquet EXISTS on disk. Setting forecast_eligible=True.",
                station_id, pm25_status,
            )

        forecast_eligible = disk_eligible

        row["forecast_eligible"] = str(forecast_eligible)
        row["available_pollutants"] = ";".join(available_pollutants)
        row["pm25_forecast_coverage_status"] = pm25_status

        results.append(row)

    return results


def write_registry_csv(project_root: Path, rows: list[dict]) -> None:
    registry_path = project_root / "data" / "reference" / "bengaluru_station_registry.csv"
    fieldnames = list(rows[0].keys()) if rows else []

    with registry_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Wrote %d stations to %s", len(rows), registry_path)


def main() -> None:
    project_root = _get_project_root()
    logger.info("Project root: %s", project_root)
    rows = compute_station_capabilities(project_root)
    write_registry_csv(project_root, rows)

    for r in rows:
        sid = r["station_id"]
        logger.info(
            "  %s: eligible=%s  pollutants=%s  pm25_status=%s",
            sid, r["forecast_eligible"], r["available_pollutants"], r["pm25_forecast_coverage_status"],
        )


if __name__ == "__main__":
    main()
