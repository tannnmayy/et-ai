# Features & Scoring Reference

This document describes the formulas AQI Sentinel actually uses. It separates an evidence-backed signal from a product-display transformation and calls out every intentional approximation. All source shares below are fractions in `[0, 1]` unless stated otherwise.

## 1. Design principle: useful, inspectable, and bounded

The platform uses several different scores because they answer different questions:

| Score | Question answered | Range | Do not read it as |
| --- | --- | ---: | --- |
| Source attribution share | “Which source categories are most consistent with nearby, upwind context?” | sums to 1 | proof of a specific polluter |
| Fused PM2.5 | “What station-anchored concentration estimate can be shown here?” | µg/m³ or unavailable | a sensor reading outside fusion range |
| Attribution confidence | “How much should this local evidence mix be trusted?” | 0–100 | probability of causality |
| Base enforcement priority | “Where is an intervention likely to matter most?” | non-negative, normally < 1 | a legal severity score |
| Risk-adjusted priority | “Which targets remain most credible after confidence is applied?” | non-negative, normally < 1 | an AQI value |
| Citizen match | “How well does this locality fit this profile?” | 0–100% | a guarantee of health, rent, or travel time |

## 2. Source attribution

### What is modelled

For a selected H3 resolution-9 cell, the detailed attribution engine examines neighbouring cells within a **3 km** radius. It derives four source categories from separate evidence layers:

| Category | Evidence used by detailed selected-cell attribution |
| --- | --- |
| Traffic | OSM road density with an optional major-corridor blend, modulated by Sentinel-5P NO₂ where available; time-of-day multiplier applied before normalization |
| Industrial | OSM industrial land-use fraction and mapped industrial-facility count, modulated by Sentinel-5P NO₂ where available |
| Construction | OSM construction-feature count |
| Burning | NASA FIRMS detection count where available; a very small floor prevents a zero-total arithmetic edge case |

Let target cell be `T`, source cell be `i`, `dᵢ` the distance in metres, `bᵢ→T` the bearing from source to target, and `w` the meteorological wind direction **from** which wind is reported. Air movement direction is `(w + 180) mod 360`.

For usable wind, the spatial weight is:

```text
directionᵢ = max(0, cos(bᵢ→T − air_movement_direction))
weightᵢ = directionᵢ / max(dᵢ, 1)
```

For each source category `c`, the engine computes:

```text
contribution_c = Σᵢ(raw_intensityᵢ,c × weightᵢ)
attribution_c  = contribution_c / Σₖ contribution_k
```

The `max(0, cosine)` term only allows upwind-to-downwind support; inverse distance makes nearer source context matter more. This is a deliberately lightweight **directional weighting proxy**, not a full atmospheric-dispersion model.

### Raw intensity formulas

With `rᵢ` = road density, `qᵢ` = major-road corridor score, `nᵢ` = normalized Sentinel-5P NO₂ modulation, `Iᵢ` = industrial land-use fraction, `Fᵢ` = industrial facility count, `Cᵢ` = construction-feature count, and `Bᵢ` = FIRMS detection count:

```text
traffic_densityᵢ = 0.6rᵢ + 0.4qᵢ                 # when corridor data exists
traffic_rawᵢ     = nᵢ × (0.7 × traffic_densityᵢ + 0.3)
industrial_rawᵢ  = nᵢ × (0.8Iᵢ + 0.2Fᵢ + 0.1)
construction_rawᵢ = Cᵢ + 0.1
burning_rawᵢ      = Bᵢ + 0.01                     # FIRMS context available
```

If Sentinel-5P NO₂ is unavailable, `nᵢ = 1`. If FIRMS is unavailable, burning receives only the small `0.01` floor; the API should be read as lacking a live burning detection signal rather than confirming that burning is absent.

### Wind and time-of-day safeguards

- At wind speed **≤ 1 km/h** or missing wind direction, direction is unreliable. The engine changes `method` to `calm_fallback` and uses `weightᵢ = 1 / max(dᵢ, 1)` without directional claims.
- Traffic is multiplied before attribution normalization using Bengaluru local time:

| Local time | Traffic multiplier |
| --- | ---: |
| 07:00–09:59 and 17:00–19:59 | 1.4 |
| 10:00–16:59 | 1.1 |
| all other hours | 0.7 |

These traffic multipliers are explicit operational assumptions, not measured live vehicle counts. The API accepts `simulated_hour=0…23` so judges can compare a peak and off-peak response.

## 3. PM2.5 fusion: bridging sparse stations without inventing coverage

AQI Sentinel does **not** claim a live PM2.5 value for every cell. Fusion only runs when at least one forecast-eligible station with a valid PM2.5 reading lies within **5 km**. Outside that range, `fused_pm25 = null` / unavailable.

The selected-cell fusion path uses two steps:

1. **Attribution-similarity baseline.** Let `a_T` and `aⱼ` be the four-category attribution vectors for the target and station `j`.

   ```text
   similarityⱼ = max(0, 1 − ||a_T − aⱼ||₁ / 2)
   baseline(T) = weighted_mean(PM2.5ⱼ, similarityⱼ)
   ```

   If all similarity weights are zero, it uses the mean of in-range station readings as a conservative fallback.

2. **Inverse-distance residual correction.** Each station’s observed residual versus its own similarity-weighted baseline is interpolated:

   ```text
   residual_correction(T) = Σⱼ(residualⱼ / max(dⱼ, 1)) / Σⱼ(1 / max(dⱼ, 1))
   fused_PM2.5(T) = baseline(T) + residual_correction(T)
   ```

The citywide enforcement path uses a faster, vectorized bounded IDW estimate from current station readings. It is deliberately marked `vectorised_feature_proxy` and confidence is penalized slightly because it does not rerun full plume transfer for every cell.

## 4. Attribution confidence

Attribution confidence answers *how much weight should we place on the investigation signal?* It starts at 100 and applies transparent deductions.

| Condition | Score effect |
| --- | ---: |
| Nearest station ≤1 km | 0 |
| 1–2.5 km from station | −15 |
| 2.5–4 km from station | −30 |
| 4–5 km from station | −45 |
| No station anchor within fusion range | −32 |
| Fast citywide feature-proxy path | −5 |
| Calm-wind distance fallback | −15 |
| Attribution unavailable | −30 |
| No fused station anchor | −12 |
| Only one station contributes | −6 |

Scores are clipped to `[0, 100]` and labelled **High** (≥80), **Medium** (≥55), **Low** (≥30), or **Very Low**. A valid non-unavailable feature-based method receives a display floor of 18 so it is not visually mistaken for a system failure; the reason and flags remain exposed.

## 5. Enforcement priority

### Why this formula

An enforcement queue should not simply rank the dirtiest cell. AQI Sentinel ranks where an intervention is most likely to matter, considering who is exposed, how much of the signal is linked to actionable categories, and whether the suspected category is realistically addressable.

The server’s base ranking is:

```text
Priority = Exposure × AttributableMagnitude × Actionability × CorridorLift
```

### 5.1 Exposure

Let `V` be the number of vulnerability POIs in the cell (schools, hospitals, elderly-care context) and `R` be residential land-use fraction.

```text
vulnerability_weight = min(1, V / 3)
residential_weight    = min(1, R / 0.5)
Exposure              = 0.7 × vulnerability_weight + 0.3 × residential_weight
```

If the vulnerability layer is absent, the engine switches to a residential-fraction proxy and reports that source status.

### 5.2 Actionable magnitude

Let `P` be fused PM2.5, `t, i, c, b` be traffic, industrial, construction, and burning attribution fractions, and `q` be corridor score.

```text
enforceable_fraction = i + c + b
traffic_magnitude    = 0.95 × t × q
magnitude_fraction   = min(1.5, enforceable_fraction + traffic_magnitude)

AttributableMagnitude = min(1, P × magnitude_fraction / 300)
```

Construction, industrial, and burning are treated as directly inspectable categories. Traffic gains magnitude only where a major-road-corridor signal exists, avoiding a bias toward diffuse residential traffic.

### 5.3 Actionability

Source actionability weights are intentionally explicit policy choices:

| Source | Weight | Rationale |
| --- | ---: | --- |
| Industrial | 1.00 | Mapped facilities can be inspected for emissions compliance. |
| Construction | 1.00 | Dust-control measures and permits are directly inspectable. |
| Burning | 1.00 | Open burning is directly enforceable once located. |
| Traffic | `0.42 + 0.28q` | Vehicle/corridor interventions are actionable, but less site-specific; their weight rises on major corridors. |

```text
Actionability = t × (0.42 + 0.28q) + i + c + b
```

### 5.4 Corridor lift and risk adjustment

```text
CorridorLift = 1 + 0.50 × q × t
BasePriority = Exposure × AttributableMagnitude × Actionability × CorridorLift

ConfidenceFactor = 0.35 + 0.65 × AttributionConfidence / 100
RiskAdjustedPriority = BasePriority × ConfidenceFactor
```

The normal view sorts by `BasePriority`. **Risk-Adjusted View** sorts by `RiskAdjustedPriority`; it can change the order of targets, which is intentional. A low-confidence high score remains visible but should not outrank a comparably actionable, better-supported target.

### 5.5 What the 0–10 UI score means

The backend score is deliberately a small multiplicative signal. The enforcement table presents a readable **0–10 display score** that preserves rank and includes absolute signal:

```text
rank_component = clamp(10.5 − 0.55 × (rank − 1), 1.5, 10)
absolute_component = clamp(5 × log10(1 + 200 × backend_priority), 0, 10)
display_score = round_to_1dp(0.65 × rank_component + 0.35 × absolute_component)
```

The display score is for operator readability. The underlying `priority_score`, `risk_adjusted_score`, exposure, magnitude, actionability, and confidence factor are returned in the API payload so the ranking remains auditable.

### 5.6 Labels, tiers, and counterfactual

- A source label is **Traffic**, **Industrial**, **Construction**, or **Burning** only when its share is at least 80%; otherwise it is labelled **Mixed**.
- Display action tier: `Immediate` requires score ≥9 and high/critical exposure; `High` ≥7; `Monitor` ≥5; otherwise `Routine`.
- The construction what-if accepts `construction_scale` in `[0, 2]`, scales its attribution channel, renormalizes the fractions, and re-runs the citywide priority formula. It is a sensitivity analysis, not a forecast of realised air-quality improvement.

## 6. Forecasting, model choice, and forecast confidence

### 6.1 24-hour PM2.5 prediction

The pooled model uses lagged PM2.5 / PM10 / NO₂, calendar cyclic features, temperature, humidity, rainfall, rolling PM2.5 statistics, station identity, and station interactions for five predictors (`no2_lag_1h`, `no2_lag_24h`, `pm25_roll_std_24h`, `hour_sin`, `temperature_c`).

For every forecast-eligible station, AQI Sentinel compares:

```text
Persistence forecast = observed PM2.5 at t − 24 hours
LightGBM forecast    = f(lags, weather, calendar, rolling features, station interactions)
```

The API serves whichever has the lower held-out **test RMSE for that station**. This is why persistence remains a first-class outcome rather than a hidden fallback.

Forecast uncertainty is displayed as approximately:

```text
[max(0, prediction − selected_test_RMSE), prediction + selected_test_RMSE]
```

This is a roughly 68% residual-normal approximation, not a calibrated 95% prediction interval.

### 6.2 Forecast-data confidence

Independently from model selection, station data confidence starts at 100 and subtracts penalties for stale observations, incomplete recent PM2.5, large time gaps, and lower quality class.

| Rule | Penalty |
| --- | ---: |
| Latest observation >3h / >12h old | −20 / −35 |
| Recent PM2.5 completeness <75% / <50% | −15 / −25 |
| Recent PM2.5 gap >6h / >24h | −20 / −30 |
| “Usable with caveats” / “Not suitable” station classification | −15 / −40 |

The result is clamped to 0–100 and labelled High (≥80), Medium (≥55), Low (≥25), or Unavailable. Forecast-ineligible stations are explicitly unavailable for PM2.5 forecast/fusion, not imputed.

## 7. Citizen Mode matching

### 7.1 Component scores

Each candidate locality receives normalized components in `[0,1]`.

```text
AQI_fit = clamp(1 − PM2.5 / 200, 0, 1)

rent_fit = 0.85 + 0.15 × rent/budget,                       when rent ≤ budget
         = 1 − (rent/budget − 1) / 0.50,                    when budget < rent < 1.5×budget
         = 0,                                               when rent ≥ 1.5×budget

commute_fit = 1,                                            when commute ≤ 0.5 × limit
            = 1 − 0.4 × (commute − 0.5×limit)/(0.5×limit), when 0.5×limit < commute ≤ limit
            = 0,                                            when commute > limit
```

Parks, hospitals, and schools use their 0–100 feature score divided by 100. Noise is inverted. Metro fit is `clamp(1 − metro_distance_km / 3, 0, 1)` when metro data exists.

### 7.2 Weights and personalisation

Default weights are:

| Rent | AQI | Commute | Parks | Hospitals | Schools | Noise | Metro |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.30 | 0.25 | 0.25 | 0.05 | 0.05 | 0.05 | 0.05 | 0.00 |

A selected priority adds +0.20 to low AQI or +0.15 to the relevant amenity/noise/metro weight. Each of respiratory condition, elderly household, and young children adds +0.05 to AQI. Weights are then normalized to sum to 1:

```text
Match% = 100 × Σ(feature_weight × component_score)
```

To avoid unnecessary paid routing calls, the engine first estimates commute with a 18 km/h Bengaluru proxy, keeps candidates within 1.25× the requested limit, and then refines up to 20 shortlisted candidates through Google Routes if configured. Any result still using the proxy is labelled estimated.

## 8. What-if PM2.5 simulation

Let `sₖ` be the current attribution share of source `k` and `fₖ` its requested scale (`0.5` means reduce to 50% of baseline). AQI Sentinel uses the bounded linear local approximation:

```text
removed_fraction = Σₖ sₖ × (1 − fₖ)
retained_fraction = clamp(1 − removed_fraction, 0.05, 2.0)
simulated_PM2.5 = baseline_PM2.5 × retained_fraction
```

The simulation reports a ±30% band around the **estimated change**. It is useful for comparing intervention hypotheses, but it does not model nonlinear chemistry, regional transport, meteorology changes, or a verified emissions inventory.

## 9. Where to inspect the implementation

| Topic | Primary implementation |
| --- | --- |
| Detailed attribution and selected-cell fusion | `backend/app/services/attribution_service.py` |
| Citywide priority engine | `backend/app/services/enforcement_priority_service.py` |
| Bounded IDW map fusion | `backend/app/services/fusion_estimation_service.py` |
| Attribution confidence | `backend/app/services/attribution_confidence_service.py` |
| Forecasting and serving | `ml/train_lightgbm.py`, `backend/app/services/forecast_service.py` |
| Citizen matching | `backend/app/services/citizen_matching_service.py` |
| Scenario simulation | `backend/app/services/whatif_scenario_service.py` |
| UI score presentation | `frontend/src/services/geospatialService.ts` |

For source provenance and the complete runtime flow, continue to [Architecture & Data Flow](ARCHITECTURE_AND_DATA_FLOW.md).

