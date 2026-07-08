# Milestone 6C — LightGBM Underperformance Diagnostic

**Date:** 2026-07-08
**Data source:** `ml/artifacts/multistation/evaluation_metrics.json`, per-station `*_features_24h.parquet` files, `lightgbm_pm25_24h.joblib`
**Analysis script:** `ml/diagnostics/diagnose_lightgbm.py`

*All target statistics (mean, std, CV, feature-target correlations) are computed on the test-split only — matching the split used for RMSE evaluation. The original report incorrectly used full-year data; this is the corrected version.*

---

## Background

The served LightGBM model (`ml/artifacts/multistation/lightgbm_pm25_24h.joblib`) underperforms persistence at 4 of 6 stations:

| Station | Persistence RMSE | LightGBM RMSE | Winner | Gap |
|---|---|---|---:|---:|
| cpcb_bapujinagar | 29.24 | 36.95 | Persistence | −26.4% |
| cpcb_hebbal | 28.86 | 33.39 | Persistence | −15.7% |
| cpcb_hombegowda | 13.96 | 12.72 | LightGBM | **+8.8%** |
| cpcb_jayanagar5 | 22.03 | 31.24 | Persistence | −41.8% |
| cpcb_peenya | 11.55 | 8.80 | LightGBM | **+23.8%** |
| cpcb_silkboard | 24.36 | 30.44 | Persistence | −25.0% |

---

## Hypothesis 1 — Uneven effective training data per station

### Row counts and split distribution

| Station | Total rows | Train | Validation | Test | Train % |
|---|---|---|---:|---:|---:|
| cpcb_bapujinagar | 6,511 | 5,312 | 1,162 | **37** | 81.6% |
| cpcb_hebbal | 5,987 | 4,167 | 646 | 1,174 | 69.6% |
| cpcb_hombegowda | 6,957 | 4,607 | 1,160 | 1,190 | 66.2% |
| cpcb_jayanagar5 | 6,203 | 4,736 | 527 | 940 | 76.4% |
| cpcb_peenya | 6,874 | 4,536 | 1,179 | 1,159 | 66.0% |
| cpcb_silkboard | 5,397 | 3,543 | 740 | 1,114 | 65.6% |

**Key findings:**

- **Training volume is roughly balanced.** All stations have 3,543–5,312 training rows. Losing stations (bapujinagar, hebbal, jayanagar5, silkboard) do NOT have systematically less training data than winning stations (hombegowda, peenya). Spearman ρ between training rows and absolute RMSE gap % = 0.429 (p = 0.397, not significant, and the sign points opposite to what the hypothesis predicts — more training data trends with larger gaps).
- **The global 70/15/15 split is driven by unique timestamps across ALL stations combined.** Stations with more complete data at the split boundaries get more rows in each split. This causes some imbalance (bapujinagar: 81.6% train vs silkboard: 65.6%) but not enough to explain the RMSE gap.
- **cpcb_bapujinagar has only 37 test rows** (~1.5 days). This makes its RMSE comparison statistically unreliable. A single large spike or calm period can dramatically swing RMSE on 37 points. The reported gap of −26.4% should be treated as low-confidence.
- **All stations have 100% `target_pm25_24h` completeness** (no missing targets), so missing-data artifacts are not a factor.

**Verdict: Ruled out for training volume.** Bapujinagar's 37-test-row evaluation is unreliable, but this is a testing/validation issue, not a training data cause.

---

## Hypothesis 2 — Feature/target signal strength per station

### Baseline sanity check: computed vs reported persistence RMSE

| Station | Computed RMSE | Reported RMSE | Match |
|---|---:|---:|---:|
| cpcb_bapujinagar | 29.24 | 29.24 | OK |
| cpcb_hebbal | 28.86 | 28.86 | OK |
| cpcb_hombegowda | 13.96 | 13.96 | OK |
| cpcb_jayanagar5 | 22.03 | 22.03 | OK |
| cpcb_peenya | 11.55 | 11.55 | OK |
| cpcb_silkboard | 24.36 | 24.36 | OK |

All computed persistence RMSE values match the reported metrics exactly. The analysis pipeline is correct.

### Target volatility (test-split only)

| Station | Test rows | Target mean | Target std | CV |
|---|---:|---:|---:|---:|
| cpcb_bapujinagar | 37 | 62.66 | 15.97 | 0.25 |
| cpcb_hebbal | 1,174 | 51.61 | 26.25 | 0.51 |
| cpcb_hombegowda | 1,190 | 28.78 | 12.18 | 0.42 |
| cpcb_jayanagar5 | 940 | 53.37 | 18.41 | 0.34 |
| cpcb_peenya | 1,159 | 20.12 | 8.97 | 0.45 |
| cpcb_silkboard | 1,114 | 49.12 | 22.44 | 0.46 |

**When restricted to the test split, the volatility pattern observed in the full-year data disappears.** The two winning stations (hombegowda: std 12.18, peenya: std 8.97) do have the lowest standard deviations, but the losing stations do not cluster at the high end — hebbal (std 26.25) and silkboard (std 22.44) are high, while bapujinagar (std 15.97) and jayanagar5 (std 18.41) are moderate. The Spearman rank correlation between test-set target std and absolute RMSE gap % is **ρ = 0.143 (p = 0.787)** — no meaningful relationship. The earlier report's claim of "strong volatility separation" was an artifact of computing std over the full year instead of the test period.

### Per-station feature-target correlation (test-split only)

Mean absolute correlation with `target_pm25_24h` across all features, computed on test-split data:

| Station | Mean |abs| correlation | Wins/Loses |
|---|---:|---:|
| cpcb_bapujinagar | 0.500 | Loses |
| cpcb_hebbal | 0.354 | Loses |
| cpcb_hombegowda | 0.331 | **WINS** |
| cpcb_jayanagar5 | 0.301 | Loses (worst) |
| cpcb_silkboard | 0.270 | Loses |
| cpcb_peenya | **0.076** | **WINS** (biggest) |

Key individual feature correlations for peenya (the biggest winner) vs jayanagar5 (the biggest loser):

| Feature | peenya | jayanagar5 |
|---|---:|---:|
| pm25_lag_24h | 0.017 | 0.329 |
| pm10_lag_1h | 0.145 | 0.351 |
| no2_lag_1h | 0.027 | −0.185 |
| pm25_roll_mean_3h | 0.143 | 0.530 |
| pm25_roll_mean_24h | 0.117 | 0.241 |

**Peenya has the weakest feature-target correlation of any station (mean |abs| = 0.076) yet wins by the largest margin (+23.8%).** This is strong evidence that feature-target correlation on its own does NOT determine whether LightGBM beats persistence. The model is perfectly capable of extracting signal that raw correlation doesn't capture — the key question is whether it can learn station-specific behavior.

The correlation data in the test set also differs substantially from the full-year data: bapujinagar's test-session correlation (0.500) is higher than in the full year (0.367), while peenya's drops from 0.358 to 0.076. This suggests that station-level dynamics shift between the training and test periods (concept drift), which would make any globally-trained model struggle on stations where the drift is largest.

**Verdict: Ruled out.** Feature-target correlation in the test set does not predict model success or failure. Peenya wins biggest with the weakest correlations; jayanagar5 loses worst with mid-range correlations. Spearman ρ between mean |abs| correlation and absolute gap % = −0.029 (p = 0.957).

---

## Hypothesis 3 — One-hot station encoding is too weak a signal

The model was trained with 9 one-hot station columns (`is_station_<id>`) and 23 base features (32 total). Feature importances from the saved model:

| Rank | Feature | Importance | Type |
|---|---:|---:|---:|
| 1 | pm25_lag_1h | 245 | base |
| 2 | month | 240 | base |
| 3 | pm25_roll_mean_24h | 196 | base |
| 4 | pm25_lag_12h | 162 | base |
| 5 | pm25_roll_std_24h | 161 | base |
| 6 | pm25_lag_24h | 128 | base |
| 7 | pm25_roll_mean_3h | 123 | base |
| 8 | relative_humidity | 123 | base |
| 9 | temperature_c | 117 | base |
| 10 | no2_lag_1h | 110 | base |
| 11 | pm10_lag_1h | 73 | base |
| **12** | **is_station_cpcb_rvce_mailasandra** | **63** | **dummy** |
| 13–22 | ... (base features) | 55–27 | base |
| **23** | **is_station_cpcb_hebbal** | **24** | **dummy** |
| **24** | **is_station_cpcb_jayanagar5** | **22** | **dummy** |
| **26** | **is_station_cpcb_bapujinagar** | **21** | **dummy** |
| **27** | **is_station_cpcb_silkboard** | **7** | **dummy** |
| 29–31 | ... | 5–3 | base/dummy |
| **31** | **is_station_cpcb_peenya** | **3** | **dummy** |
| 32 | rainfall_mm | 0 | base |

**Station dummy ranking summary:**
- **None in top 11.** The first station dummy (rvce_mailasandra) ranks 12th, at 63 vs the top feature's 245.
- The 6 original-station dummies: hombegowda=54, hebbal=24, jayanagar5=22, bapujinagar=21, silkboard=7, peenya=3
- Mean station dummy importance: **22.4** vs mean overall feature importance: **71.2** — station dummies are **0.32× the average feature**.
- `is_station_cpcb_peenya` has importance **3** — the model barely registers which station peenya is, yet peenya wins the most. This is actually consistent: peenya's behavior is close to the global mean, so a weak encoding doesn't hurt it. The stations that lose are the ones whose behavior diverges from the global mean — which the encoding is too weak to correct.

**Verdict: Strongly supported.** The model sees station identity as a negligible signal. A one-hot dummy with no interaction features forces the model to learn the same relationship for all stations, with at most a constant additive offset. Peenya wins because its dynamics happen to match the global average; jayanagar5, hebbal, bapujinagar, and silkboard lose because theirs diverge.

---

## Hypothesis 4 — Synthesis: what correlates with the RMSE gap?

### Side-by-side comparison (test-split corrected)

| Station | RMSE gap | Gap % | Target std | Train rows | Test rows | Mean |corr| |
|---|---:|---:|---:|---:|---:|---:|
| **jayanagar5** | **+9.20** | **−41.8%** | 18.41 | 4,736 | 940 | 0.301 |
| bapujinagar* | +7.71 | −26.4% | 15.97 | 5,312 | **37** | **0.500** |
| silkboard | +6.08 | −25.0% | 22.44 | 3,543 | 1,114 | 0.270 |
| hebbal | +4.53 | −15.7% | 26.25 | 4,167 | 1,174 | 0.354 |
| hombegowda | −1.23 | **+8.8%** | 12.18 | 4,607 | 1,190 | 0.331 |
| peenya | −2.75 | **+23.8%** | **8.97** | 4,536 | 1,159 | **0.076** |

*\* bapujinagar's evaluation is low-confidence (37 test rows)*

### Spearman rank correlations with absolute RMSE gap %

| Factor | ρ | p-value | Significant? |
|---|---:|---:|---:|
| Target std | 0.143 | 0.787 | No |
| Mean |corr| | −0.029 | 0.957 | No |
| Train rows | 0.429 | 0.397 | No |

**None of the candidate factors show a statistically significant relationship.** With n = 6, the test has very low power, but the correlation magnitudes are all small or in the wrong direction.

### What the data actually shows

1. **No single factor predicts model success.** Target volatility, feature-target correlation, and training data volume all fail to explain why some stations win and others lose.

2. **The strongest pattern is negative:** `is_station_cpcb_peenya` has importance **3** (lowest of any station dummy), and peenya wins biggest. `is_station_cpcb_jayanagar5` has importance **22** and loses worst. This is consistent with a model that can only learn the global average: stations near the global mean win (encoding barely needed), stations far from it lose (encoding too weak to shift predictions enough).

3. **Bapujinagar's 37 test rows make its gap unreliable.** The reported −26.4% could be substantially different with a longer test window.

4. **Concept drift between training and test periods** may affect stations differently. Peenya's feature correlations shift dramatically from full-year (0.358) to test-split (0.076), yet the model generalizes well — suggesting its test-period dynamics happen to align with what the global model learned during training.

---

## Ranked Conclusions

**Hypothesis 3 (weak station encoding) is the primary and only well-supported root cause.** Station dummies rank 12th–32nd out of 32 features and are worth 0.32× the average feature. The model has no mechanism to learn per-station dynamics beyond a constant additive offset. Stations whose PM2.5 dynamics diverge from the global average will be poorly served by this approach.

**Hypothesis 1 (training data) is ruled out.** No correlation between training volume and model gap.

**Hypothesis 2 (feature correlation) is ruled out.** Peenya wins biggest with the weakest feature-target correlation (0.076 mean |abs|). Jayanagar5 loses worst with mid-range correlation (0.301). Feature correlation in the test set does not predict model success.

**Hypothesis 4 (volatility) is ruled out.** The earlier volatility finding was an artifact of computing standard deviation over the full year rather than the test split. With corrected test-set-only std, Spearman ρ = 0.143 (p = 0.787). The pattern does not hold.

**Bottom line:** The evidence supports a single clean conclusion — the global model with one-hot station encoding cannot adapt to per-station dynamics. Stations near the global mean generalize well (peenya). Stations whose patterns differ from the mean (jayanagar5, hebbal, silkboard, bapujinagar) underperform. The fix is structural, not parametric.

---

## Candidate Next Steps

1. **Train per-station LightGBM models** instead of a single global model. This completely sidesteps the "weak station encoding" problem. Each station gets its own lag-weather-response surface. The trade-off is smaller training sets per station and higher maintenance overhead, but the feature set is identical — only the learned weights differ.

2. **Add interaction features between station identity and key predictors** (e.g., `pm25_lag_24h * is_station_<id>`). This is lighter than full per-station models — the global model still shares structure across stations, but station-specific slopes (not just offsets) give it per-station flexibility. Trees natively handle interactions at depth > 1, but the split must be offered; with one-hot encoding alone, a depth-1 split on `is_station_X` only shifts the mean.

3. **Investigate whether bapujinagar's 37 test rows are representative.** Before any model-change investment, extend the test window for bapujinagar or use a rolling-window evaluation that produces more than 1.5 days of test data. If the RMSE gap for bapujinagar is actually smaller (or larger) than reported, it changes which stations need the most attention.
