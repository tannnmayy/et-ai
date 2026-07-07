# Hebbal CPCB/KSPCB Data Quality Report

Generated at (UTC): 2026-07-07T15:58:42.143996+00:00

## Source
- Raw file: `E:\1ETAI\data\raw\cpcb\bwssb_kadabesanahalli_bengaluru_cpcb_15m.csv`
- Station: `BWSSB Kadabesanahalli` (`cpcb_kadabesanahalli`)
- Source label: CPCB

## Raw CSV Inspection
- Detected headers: `Timestamp, PM2.5 (µg/m³), PM10 (µg/m³), NO (µg/m³), NO2 (µg/m³), NOx (ppb), NH3 (µg/m³), SO2 (µg/m³), CO (mg/m³), Ozone (µg/m³), Benzene (µg/m³), Toluene (µg/m³), Xylene (µg/m³), O Xylene (µg/m³), Eth-Benzene (µg/m³), MP-Xylene (µg/m³), AT (°C), RH (%), WS (m/s), WD (deg), RF (mm), TOT-RF (mm), SR (W/mt2), BP (mmHg), VWS (m/s)`
- Raw row count: 11712
- Cleaned 15-minute rows: 11712
- Hourly rows: 2929
- Earliest UTC timestamp: 2025-08-31T18:30:00+00:00
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
- Expected 15-minute intervals: 11712
- Observed 15-minute intervals: 11712

## Missingness
### 15-minute
- pm25: 53.33%
- pm10: 46.56%
- no2: 43.55%
- temperature_c: 76.79%
- relative_humidity: 77.99%
- wind_speed_mps: 92.46%
- rainfall_mm: 100.0%

### Hourly
- pm25: 52.44%
- pm10: 45.1%
- no2: 43.22%
- temperature_c: 76.72%
- relative_humidity: 77.53%
- wind_speed_mps: 92.39%
- rainfall_mm: 0.0%

## Hourly PM2.5 Controls
- Minimum PM2.5 observations per hour: 2
- Hours excluded for insufficient PM2.5: 1536
- Longest continuous hourly PM2.5 run (hours): 351
- PM2.5 gaps longer than 24 hours: 3

## Rainfall
Rainfall column is entirely missing; hourly rainfall remains null.

## Suitability
- Classification: **Not suitable**
- Recommendation: Coverage, PM2.5 completeness, or continuity fall below the minimum thresholds for reliable 24-hour PM2.5 training.
- Limitation: One station validates the real-data pipeline; it does not yet prove citywide generalization.
