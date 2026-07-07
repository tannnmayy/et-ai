# Hebbal CPCB/KSPCB Data Quality Report

Generated at (UTC): 2026-07-07T15:59:21.264499+00:00

## Source
- Raw file: `E:\1ETAI\data\raw\cpcb\sanegurava_halli_bengaluru_kspcb_15m.csv`
- Station: `Sanegurava Halli` (`cpcb_saneguravahalli`)
- Source label: KSPCB

## Raw CSV Inspection
- Detected headers: `Timestamp, PM2.5 (µg/m³), PM10 (µg/m³), NO (µg/m³), NO2 (µg/m³), NOx (ppb), NH3 (µg/m³), SO2 (µg/m³), CO (mg/m³), Ozone (µg/m³), Benzene (µg/m³), Toluene (µg/m³), Xylene (µg/m³), O Xylene (µg/m³), Eth-Benzene (µg/m³), MP-Xylene (µg/m³), AT (°C), RH (%), WS (m/s), WD (deg), RF (mm), TOT-RF (mm), SR (W/mt2), BP (mmHg), VWS (m/s)`
- Raw row count: 35040
- Cleaned 15-minute rows: 35040
- Hourly rows: 8761
- Earliest UTC timestamp: 2024-12-31T18:30:00+00:00
- Latest UTC timestamp: 2025-12-31T18:15:00+00:00

## Timestamp Handling
- Interpretation: Raw timestamps are timezone-naive station readings. They are localized to Asia/Kolkata and converted to UTC.
- Source timezone assumption: Asia/Kolkata
- UTC conversion: Naive timestamps -> localize(Asia/Kolkata) -> tz_convert(UTC). Invalid or ambiguous local timestamps are set to null.
- Invalid timestamps: 0

## Cleaning Summary
- Duplicate timestamps resolved: 0
- Numeric conversion failures: `{"pm25": 0, "pm10": 0, "no2": 0, "temperature_c": 0, "relative_humidity": 0, "wind_speed_mps": 0, "rainfall_mm": 0, "latitude": 0, "longitude": 0}`
- Negative-value rejections: `{}`
- Plausibility flags: `{"pm25": 0, "pm10": 0, "no2": 0, "relative_humidity": 0, "temperature_c": 0, "wind_speed_mps": 0, "rainfall_mm": 0}`
- Expected 15-minute intervals: 35040
- Observed 15-minute intervals: 35040

## Missingness
### 15-minute
- pm25: 100.0%
- pm10: 5.15%
- no2: 3.88%
- temperature_c: 5.68%
- relative_humidity: 5.11%
- wind_speed_mps: 27.78%
- rainfall_mm: 100.0%

### Hourly
- pm25: 100.0%
- pm10: 4.68%
- no2: 3.36%
- temperature_c: 5.14%
- relative_humidity: 4.66%
- wind_speed_mps: 20.36%
- rainfall_mm: 0.0%

## Hourly PM2.5 Controls
- Minimum PM2.5 observations per hour: 2
- Hours excluded for insufficient PM2.5: 8761
- Longest continuous hourly PM2.5 run (hours): 0
- PM2.5 gaps longer than 24 hours: 0

## Rainfall
Rainfall column is entirely missing; hourly rainfall remains null.

## Suitability
- Classification: **Not suitable**
- Recommendation: Coverage, PM2.5 completeness, or continuity fall below the minimum thresholds for reliable 24-hour PM2.5 training.
- Limitation: One station validates the real-data pipeline; it does not yet prove citywide generalization.
