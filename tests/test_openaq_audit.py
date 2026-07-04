import pandas as pd

from pipeline.audit_openaq_bengaluru import (
    BoundingBox,
    aggregate_hourly_long_form,
    build_station_hourly_wide,
    calculate_station_quality_metrics,
    classify_station,
    generate_markdown_report,
    longest_continuous_run_hours,
    normalize_hourly_measurements,
)
from pipeline.openaq_client import OpenAQLocation, OpenAQSensor


def _location():
    return OpenAQLocation(
        location_id=123,
        name="Bengaluru Station",
        latitude=12.97,
        longitude=77.59,
        locality="Bengaluru",
        country_code="IN",
        country_name="India",
        is_active=True,
        raw={},
    )


def _sensor(parameter="pm25", units="µg/m³"):
    return OpenAQSensor(sensor_id=456, location_id=123, parameter=parameter, units=units, raw_parameter_name=parameter, raw={})


def test_long_form_normalization_parses_timestamps_and_filters_parameters():
    measurements = [
        {
            "value": 12.5,
            "parameter": {"name": "pm25", "units": "µg/m³"},
            "period": {"datetimeFrom": {"utc": "2026-01-01T00:00:00Z"}},
        },
        {
            "value": 20.0,
            "parameter": {"name": "o3", "units": "µg/m³"},
            "period": {"datetimeFrom": {"utc": "2026-01-01T01:00:00Z"}},
        },
        {
            "value": -1.0,
            "parameter": {"name": "pm25", "units": "µg/m³"},
            "period": {"datetimeFrom": {"utc": "2026-01-01T02:00:00Z"}},
        },
    ]
    normalized = normalize_hourly_measurements(measurements, _sensor(), _location())
    assert len(normalized) == 1
    assert normalized.iloc[0]["parameter"] == "pm25"
    assert normalized.iloc[0]["timestamp_utc"] == pd.Timestamp("2026-01-01T00:00:00Z")
    assert normalized.iloc[0]["source"] == "openaq_v3"


def test_hourly_median_aggregation_is_correct():
    frame = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2026-01-01T00:10:00Z", "2026-01-01T00:40:00Z", "2026-01-01T01:00:00Z"], utc=True),
            "location_id": [123, 123, 123],
            "location_name": ["A", "A", "A"],
            "station_id": ["openaq_location_123"] * 3,
            "station_name": ["A", "A", "A"],
            "sensor_id": [456, 456, 456],
            "parameter": ["pm25", "pm25", "pm25"],
            "value": [10.0, 30.0, 50.0],
            "units": ["µg/m³"] * 3,
            "latitude": [12.0] * 3,
            "longitude": [77.0] * 3,
            "source": ["openaq_v3"] * 3,
        }
    )
    hourly, duplicate_count = aggregate_hourly_long_form(frame)
    first_hour = hourly.loc[hourly["timestamp_utc"] == pd.Timestamp("2026-01-01T00:00:00Z"), "value"].iloc[0]
    assert first_hour == 20.0
    assert duplicate_count == 1


def test_longest_continuous_pm25_run_calculation():
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=8, freq="h")
    frame = pd.DataFrame({"timestamp_utc": timestamps, "pm25": [1, 2, None, 3, 4, 5, None, 6]})
    assert longest_continuous_run_hours(frame) == 3


def test_classification_rules():
    assert classify_station(180, 70, 720)[0] == "Recommended"
    assert classify_station(90, 50, 168)[0] == "Usable with caveats"
    assert classify_station(10, 20, 3)[0] == "Not suitable"


def test_markdown_report_is_generated_from_mocked_dataset(tmp_path):
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=24 * 180, freq="h")
    wide = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "station_id": "openaq_location_123",
            "station_name": "Bengaluru Station",
            "latitude": 12.97,
            "longitude": 77.59,
            "pm25": 42.0,
            "pm10": 80.0,
            "no2": 20.0,
        }
    )
    audit = calculate_station_quality_metrics(wide)
    report_path = tmp_path / "audit.md"
    text = generate_markdown_report(audit, BoundingBox(), 180, locations_discovered=1, output_path=report_path)
    assert report_path.exists()
    assert "# OpenAQ Bengaluru Station Audit" in text
    assert "Recommended stations for Milestone 2B" in text
    assert "This audit does not train or validate a forecasting model." in text
    assert audit.iloc[0]["quality_classification"] == "Recommended"


def test_build_wide_table_schema():
    long_form = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"], utc=True),
            "station_id": ["openaq_location_123", "openaq_location_123"],
            "station_name": ["A", "A"],
            "latitude": [12.0, 12.0],
            "longitude": [77.0, 77.0],
            "parameter": ["pm25", "no2"],
            "value": [10.0, 20.0],
        }
    )
    wide = build_station_hourly_wide(long_form)
    assert list(wide.columns) == ["timestamp_utc", "station_id", "station_name", "latitude", "longitude", "pm25", "pm10", "no2"]
    assert wide.iloc[0]["pm25"] == 10.0
    assert wide.iloc[0]["no2"] == 20.0
