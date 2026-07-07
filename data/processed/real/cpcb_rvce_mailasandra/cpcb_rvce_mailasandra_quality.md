# Hebbal CPCB/KSPCB Data Quality Report

Generated at (UTC): 2026-07-07T15:59:11.692425+00:00

## Source
- Raw file: `E:\1ETAI\data\raw\cpcb\rvce_mailasandra_bengaluru_kspcb_15m.csv`
- Station: `RVCE-Mailasandra` (`cpcb_rvce_mailasandra`)
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
- pm25: 32.32%
- pm10: 40.27%
- no2: 15.45%
- temperature_c: 7.82%
- relative_humidity: 16.74%
- wind_speed_mps: 7.82%
- rainfall_mm: 7.79%

### Hourly
- pm25: 31.05%
- pm10: 36.67%
- no2: 13.07%
- temperature_c: 5.96%
- relative_humidity: 14.56%
- wind_speed_mps: 5.97%
- rainfall_mm: 0.0%

## Hourly PM2.5 Controls
- Minimum PM2.5 observations per hour: 2
- Hours excluded for insufficient PM2.5: 2720
- Longest continuous hourly PM2.5 run (hours): 315
- PM2.5 gaps longer than 24 hours: 16

## Rainfall
RF appears to represent interval rainfall; hourly rainfall uses sum of valid 15-minute RF values.

## Suitability
- Classification: **Usable with caveats**
- Recommendation: The station has enough PM2.5 history for pipeline validation, but gaps or missing auxiliary sensors should be interpreted cautiously.
- Limitation: One station validates the real-data pipeline; it does not yet prove citywide generalization.
