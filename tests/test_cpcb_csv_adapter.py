from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pipeline.cpcb_csv_adapter import (
    CPCBStationConfig,
    build_header_mapping,
    clean_cpcb_frame,
    normalize_header,
    normalize_missing_values,
    read_raw_csv,
)


HEBBAL_HEADERS = [
    "Timestamp",
    "PM2.5 (µg/m³)",
    "PM10 (µg/m³)",
    "NO (µg/m³)",
    "NO2 (µg/m³)",
    "AT (°C)",
    "RH (%)",
    "WS (m/s)",
    "RF (mm)",
]


def _write_fixture(path: Path, rows: list[list[str]]) -> None:
    lines = [",".join(HEBBAL_HEADERS)] + [",".join(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_hebbal_header_mapping_detects_actual_headers():
    mapping = build_header_mapping(HEBBAL_HEADERS)
    assert mapping["Timestamp"] == "timestamp"
    assert mapping["PM2.5 (µg/m³)"] == "pm25"
    assert mapping["PM10 (µg/m³)"] == "pm10"
    assert mapping["NO2 (µg/m³)"] == "no2"
    assert mapping["AT (°C)"] == "temperature_c"
    assert mapping["RH (%)"] == "relative_humidity"
    assert mapping["WS (m/s)"] == "wind_speed_mps"
    assert mapping["RF (mm)"] == "rainfall_mm"


def test_common_alias_mapping():
    headers = ["Date & Time", "PM2.5 (ug/m3)", "Temp", "Humidity", "Wind Speed", "Rainfall"]
    mapping = build_header_mapping(headers)
    assert mapping["Date & Time"] == "timestamp"
    assert mapping["PM2.5 (ug/m3)"] == "pm25"
    assert mapping["Temp"] == "temperature_c"
    assert mapping["Humidity"] == "relative_humidity"
    assert mapping["Wind Speed"] == "wind_speed_mps"
    assert mapping["Rainfall"] == "rainfall_mm"


def test_missing_marker_normalization():
    frame = pd.DataFrame({"PM2.5 (µg/m³)": ["62", "NA", "N/A", "-", "null"]})
    normalized = normalize_missing_values(frame)
    assert normalized.iloc[0, 0] == "62"
    assert normalized.iloc[1:, 0].isna().all()


def test_ist_to_utc_conversion(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_fixture(
        csv_path,
        [
            ["2025-01-01 00:00:00", "10", "20", "NA", "5", "25", "60", "1.0", "0.0"],
            ["2025-01-01 00:15:00", "12", "22", "NA", "6", "25", "61", "1.1", "0.0"],
        ],
    )
    station = CPCBStationConfig(station_id="cpcb_hebbal", station_name="Hebbal, Bengaluru - KSPCB")
    cleaned, stats = clean_cpcb_frame(read_raw_csv(csv_path), station, raw_path=str(csv_path))
    assert stats.source_timezone_assumption == "Asia/Kolkata"
    first = pd.Timestamp(cleaned.iloc[0]["timestamp_utc"])
    assert first.isoformat() == "2024-12-31T18:30:00+00:00"


def test_invalid_timestamp_reporting(tmp_path):
    csv_path = tmp_path / "invalid.csv"
    _write_fixture(csv_path, [["not-a-date", "10", "20", "NA", "5", "25", "60", "1.0", "0.0"]])
    station = CPCBStationConfig(station_id="cpcb_hebbal", station_name="Hebbal, Bengaluru - KSPCB")
    cleaned, stats = clean_cpcb_frame(read_raw_csv(csv_path), station, raw_path=str(csv_path))
    assert stats.invalid_timestamp_count == 1
    assert cleaned.empty


def test_negative_pm25_rejection(tmp_path):
    csv_path = tmp_path / "negative.csv"
    _write_fixture(csv_path, [["2025-01-01 00:00:00", "-5", "20", "NA", "-1", "25", "60", "-1.0", "-0.5"]])
    station = CPCBStationConfig(station_id="cpcb_hebbal", station_name="Hebbal, Bengaluru - KSPCB")
    cleaned, stats = clean_cpcb_frame(read_raw_csv(csv_path), station, raw_path=str(csv_path))
    assert pd.isna(cleaned.iloc[0]["pm25"])
    assert pd.isna(cleaned.iloc[0]["no2"])
    assert pd.isna(cleaned.iloc[0]["wind_speed_mps"])
    assert pd.isna(cleaned.iloc[0]["rainfall_mm"])
    assert stats.negative_value_rejections["pm25"] == 1


def test_duplicate_handling_uses_median(tmp_path):
    csv_path = tmp_path / "dupes.csv"
    _write_fixture(
        csv_path,
        [
            ["2025-01-01 00:00:00", "10", "20", "NA", "5", "25", "60", "1.0", "0.0"],
            ["2025-01-01 00:00:00", "20", "40", "NA", "7", "27", "62", "1.2", "0.0"],
        ],
    )
    station = CPCBStationConfig(station_id="cpcb_hebbal", station_name="Hebbal, Bengaluru - KSPCB")
    cleaned, stats = clean_cpcb_frame(read_raw_csv(csv_path), station, raw_path=str(csv_path))
    assert stats.duplicate_timestamp_count == 1
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["pm25"] == 15


def test_normalize_header_handles_unicode_variants():
    assert normalize_header("PM2.5 (µg/m³)") == "pm2.5 (ug/m3)"
    assert normalize_header("NO₂ (µg/m³)") == "no2 (ug/m3)"
