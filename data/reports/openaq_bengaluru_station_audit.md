# OpenAQ Bengaluru Station Audit

Generated at: 2026-07-04T13:39:16.442607+00:00

Bounding box: south=12.8, north=13.15, west=77.4, east=77.85
Lookback period: 365 days

Data-source disclaimer: OpenAQ aggregates public air-quality data and may not include all official monitoring data.
OpenAQ coverage can be incomplete; validate results against official CPCB exports if necessary.
This audit does not train or validate a forecasting model.

## Summary

- Locations discovered: 24
- Locations with PM2.5: 14
- Locations with PM10: 13
- Locations with NO2: 0
- Recommended stations: 0
- Usable-with-caveats stations: 11
- Not-suitable stations: 5

## Station Quality Table

| station_id | station_name | available_pollutants | covered_days | pm25_completeness_percent | longest_continuous_pm25_run_days | quality_classification |
| --- | --- | --- | --- | --- | --- | --- |
| openaq_location_3409312 | BWSSB Kadabesanahalli, Bengaluru - CPCB | pm25,pm10 | 254.25 | 74.65 | 7.71 | Usable with caveats |
| openaq_location_3409385 | RVCE-Mailasandra, Bengaluru - KSPCB | pm25,pm10 | 330.5 | 67.8 | 16.17 | Usable with caveats |
| openaq_location_3409393 | Shivapura_Peenya, Bengaluru - KSPCB | pm25,pm10 | 353.96 | 70.94 | 14.25 | Usable with caveats |
| openaq_location_5548 | BTM Layout, Bengaluru - CPCB | pm25,pm10 | 364.92 | 66.56 | 7.79 | Usable with caveats |
| openaq_location_5607 | Peenya, Bengaluru - CPCB | pm25,pm10 | 337.92 | 71.92 | 11.29 | Usable with caveats |
| openaq_location_6206921 | Koramangala | pm25 | 166.08 | 89.56 | 30.08 | Usable with caveats |
| openaq_location_6973 | Jayanagar 5th Block, Bengaluru - KSPCB | pm25,pm10 | 364.92 | 84.76 | 12.83 | Usable with caveats |
| openaq_location_6974 | Bapuji Nagar, Bengaluru - KSPCB | pm25,pm10 | 364.92 | 69.71 | 19.58 | Usable with caveats |
| openaq_location_6975 | Silk Board, Bengaluru - KSPCB | pm25,pm10 | 364.88 | 80.66 | 12.25 | Usable with caveats |
| openaq_location_6983 | Hombegowda Nagar, Bengaluru - KSPCB | pm25,pm10 | 364.92 | 87.52 | 12.83 | Usable with caveats |
| openaq_location_6984 | Hebbal, Bengaluru - KSPCB | pm25,pm10 | 364.92 | 80.13 | 10.12 | Usable with caveats |
| openaq_location_3409388 | Kasturi Nagar, Bengaluru - KSPCB | pm25,pm10 | 364.54 | 40.98 | 16.0 | Not suitable |
| openaq_location_5574 | City Railway Station, Bengaluru - KSPCB | pm10 | 364.21 | 0.0 | 0.0 | Not suitable |
| openaq_location_5644 | Sanegurava Halli, Bengaluru - KSPCB | pm10 | 333.79 | 0.0 | 0.0 | Not suitable |
| openaq_location_6119271 | Kumaraswamy Layout | pm25 | 169.58 | 22.6 | 7.17 | Not suitable |
| openaq_location_6146655 | Bellandur | pm25 | 10.79 | 81.85 | 6.38 | Not suitable |

## Recommended stations for Milestone 2B

No station meets the Recommended threshold.

## Known limitations

- OpenAQ station coverage in Bengaluru may be incomplete.
- Provider outages, sensor maintenance, and reporting gaps can affect completeness.
- Unit compatibility is enforced; incompatible or unknown units are skipped rather than converted silently.
- This phase audits data suitability only and does not retrain or validate the forecasting model.
