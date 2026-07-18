# Benchmarks & Validation

This page reports the current committed evaluation artifacts. It distinguishes measured model performance from engineering checks and names the evaluations that have **not** been completed yet.

## 1. Reproducibility snapshot

| Item | Current artifact value |
| --- | --- |
| Task | 24-hour PM2.5 forecasting |
| City | Bengaluru |
| Dataset | `real_multistation` |
| Forecast-eligible stations | 9 |
| Test rows | 8,576 |
| Split | Chronological 70/15/15 by unique timestamp, global across stations |
| Train boundary | 2025-09-12 20:00 UTC |
| Validation boundary | 2025-11-06 07:00 UTC |
| Test end | 2025-12-30 18:00 UTC |
| Metric used to select serving model | Per-station held-out test RMSE |
| Artifact | `ml/artifacts/multistation/evaluation_metrics.json` |

The chronological split prevents a model from training on future observations and then being evaluated on the past. It is preferable to a random split for a time-series forecast.

## 2. Forecast benchmark: LightGBM versus persistence

The baseline is deliberately strong:

```text
persistence prediction at t + 24h = observed PM2.5 at t
```

The pooled LightGBM model has access to pollutant lags, calendar features, rolling PM2.5 statistics, weather variables, station flags, and station-specific interaction features. It is judged against persistence rather than in isolation.

### Overall held-out results

| Model | RMSE (µg/m³) | MAE (µg/m³) | RMSE change vs persistence |
| --- | ---: | ---: | ---: |
| Persistence | 18.5552 | 11.8263 | reference |
| LightGBM | **18.4730** | 12.4724 | **0.44% lower RMSE** |

The pooled result is intentionally not overstated: LightGBM wins overall by a narrow RMSE margin, while persistence has lower pooled MAE. AQI Sentinel therefore evaluates and serves the lower-RMSE choice per station rather than declaring a universal model winner.

### Per-station held-out results

| Station | Test rows | Persistence RMSE | LightGBM RMSE | RMSE change | Selected for serving |
| --- | ---: | ---: | ---: | ---: | --- |
| Bapuji Nagar | 37 | **29.2419** | 34.1464 | −16.77% | Persistence |
| BTM Layout | 1,203 | **10.9682** | 14.9047 | −35.89% | Persistence |
| Hebbal | 1,174 | 28.8601 | **26.7217** | +7.41% | LightGBM |
| Hombegowda Nagar | 1,190 | 13.9559 | **10.5233** | +24.60% | LightGBM |
| Jayanagar 5th Block | 940 | **22.0332** | 22.1879 | −0.70% | Persistence |
| Kasturi Nagar | 1,003 | **5.7889** | 7.3354 | −26.72% | Persistence |
| Peenya | 1,159 | 11.5469 | **8.8847** | +23.06% | LightGBM |
| RVCE-Mailasandra | 756 | **18.5931** | 22.0911 | −18.81% | Persistence |
| Silk Board | 1,114 | **24.3569** | 24.5048 | −0.61% | Persistence |

**Reading the table:** a positive RMSE change means LightGBM beats persistence. The honest deployment choice is persistence at six stations and LightGBM at three. Bapuji Nagar’s test sample is only 37 rows, so its selection should be read with particular caution.

### Forecast uncertainty

The API exposes a station’s selected-model test RMSE and returns an approximate interval:

```text
prediction interval ≈ predicted PM2.5 ± selected station test RMSE
```

This is a `z = 1` residual-normal approximation (roughly 68% coverage if residuals are normal), not a calibrated 95% prediction interval. The frontend labels uncertainty Low for RMSE <12 µg/m³, Medium for 12–22, and High above 22.

## 3. Station quality and coverage validation

The data pipeline does not simply train on every available station. It builds a quality manifest with completeness and continuity information.

| Current status | Count | Treatment |
| --- | ---: | --- |
| Forecast eligible | 9 | Used in multi-station forecast evaluation and as PM2.5 fusion anchors when readings are available. |
| Recommended for real-data training | 4 | Stronger coverage/continuity in the current manifest. |
| Usable with caveats | 5 | Usable but surfaced with quality context. |
| Not forecast eligible | 3 | Retained for context where applicable; excluded from PM2.5 forecast/fusion. |

The non-eligible stations include two with no PM2.5 sensor coverage and one with too-gappy PM2.5 history. This is important: the system avoids manufacturing a forecast for a station whose target signal is unavailable.

Relevant artifacts:

- `ml/artifacts/multistation/station_manifest.json`
- `data/reports/station_coverage/station_activation_report.md`
- `data/processed/real/*/*_quality_summary.json`

## 4. Attribution and enforcement validation

### What is validated in code

The test suite covers, among other things:

- H3/geospatial construction, station coverage, artifact loading, CPCB CSV adaptation, and feature behavior;
- wind-aware attribution, calm-wind fallback, Sentinel-5P/FIRMS ingestion contracts, and confidence scoring;
- fusion, city extremes, enforcement ranking and risk-adjusted sorting;
- forecast/evaluation services;
- citizen matching and commute behavior;
- Copilot tool orchestration, map actions, language wire-up, cache behavior, and grounded response paths.

### Runtime ablation views

The Insights API includes two operational ablations that are computed from the current grid rather than hard-coded:

1. **Wind weighting versus pure distance** — reruns the selected-cell attribution with real wind and forced calm/distance weighting, then reports source changes across sampled high-signal cells.
2. **Fusion versus no fusion** — recomputes the enforcement ingredients with fused PM2.5 versus a city-median fill on the same cells, then reports top-K overlap and rank correlation.

These are useful design checks: they test whether wind and station fusion meaningfully affect outputs. They are not external ground-truth accuracy benchmarks.

## 5. Evaluations that are intentionally not claimed

| Required-style question | Current honest status |
| --- | --- |
| “How accurate is source attribution versus a ground-truth emission inventory?” | Not yet evaluated. The prototype has no matched, labelled Bengaluru emission inventory at cell/time resolution. It exposes attribution as an investigation hypothesis, not a causal finding. |
| “What is the 1 km / 24–72 hour AQI forecast accuracy?” | Not yet claimed. Current model evaluation is station-level and 24-hour only. The H3 map’s PM2.5 fusion is a bounded estimate, not an independently validated grid forecast. |
| “Did recommendations reduce pollution?” | Not yet measured. The product can log dispatch/audit activity, but no before/after controlled intervention study is included. |
| “Are citizen recommendations clinically validated?” | Not applicable/not claimed. Citizen Mode is an informational multi-criteria match, not medical or housing advice. |

This scope is a strength for judging: the product distinguishes demonstrated evidence from the next validation milestone instead of using invented accuracy numbers.

## 6. Reproduce the forecast evaluation

The checked-in artifacts already support serving. To rebuild the multi-station forecasting artifacts from the repository’s source data:

```powershell
# From repository root, with the virtual environment activated
python -m pipeline.ingest_cpcb_csv --multi-station
python -m pipeline.merge_multistation
python -m ml.train_persistence_baseline --dataset real_multistation
python -m ml.train_lightgbm --dataset real_multistation
python -m ml.evaluate --dataset real_multistation
```

Then inspect:

```powershell
Get-Content ml\artifacts\multistation\evaluation_metrics.json
Get-Content ml\artifacts\multistation\station_manifest.json
```

## 7. Run implementation checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q

Set-Location frontend
npm run lint
npm run build
```

## 8. Suggested next benchmark plan

To move from a strong hackathon prototype to operational validation:

1. Partner with a city/PCB team for time-stamped construction, compliance, and complaint records.
2. Assemble a curated emissions inventory and targeted field-sampling campaign for attribution evaluation.
3. Evaluate 24/48/72-hour predictions by station and, where portable monitors exist, by spatial holdout.
4. Track inspection precision (share of dispatched checks that find the predicted actionable issue), response time, and repeat-violation rate.
5. Test counterfactual recommendations prospectively with pre-registered outcome windows.

