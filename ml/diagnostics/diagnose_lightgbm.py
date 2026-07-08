"""
Diagnostic script for Milestone 6C — LightGBM underperformance investigation.

Computes per-station training data distribution, target statistics,
feature-target correlation, persistence RMSE, and model feature importances.
Writes no served artifacts — outputs to stdout for report generation.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ml.common import TARGET_COLUMN, chronological_split, get_paths, load_feature_data, load_selected_feature_columns
from ml.train_lightgbm import encode_station_id

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STATIONS = [
    "cpcb_bapujinagar",
    "cpcb_hebbal",
    "cpcb_hombegowda",
    "cpcb_jayanagar5",
    "cpcb_peenya",
    "cpcb_silkboard",
]


def load_data():
    """Load the multistation feature frame and apply the same chronological split."""
    project_root = Path(__file__).resolve().parents[2]
    paths = get_paths(project_root, dataset="real_multistation")
    features = load_feature_data(project_root=project_root, dataset="real_multistation")
    feature_cols = load_selected_feature_columns(project_root, dataset="real_multistation")
    features, station_encoded_cols = encode_station_id(features)
    training_feature_cols = list(feature_cols) + station_encoded_cols
    train, validation, test = chronological_split(features)
    return features, train, validation, test, training_feature_cols, project_root


def hypothesis_1(features, train, validation, test):
    """Uneven effective training data per station."""
    print("\n" + "=" * 80)
    print("HYPOTHESIS 1 — Uneven effective training data per station")
    print("=" * 80)

    split_boundaries = {
        "train_end": train["timestamp"].max(),
        "validation_end": validation["timestamp"].max(),
    }

    for station_id in STATIONS:
        total = len(features[features["station_id"] == station_id])
        train_n = len(train[train["station_id"] == station_id])
        val_n = len(validation[validation["station_id"] == station_id])
        test_n = len(test[test["station_id"] == station_id])
        train_pct = train_n / total * 100 if total > 0 else 0.0

        station_train = train[train["station_id"] == station_id]
        station_test = test[test["station_id"] == station_id]

        train_daterange = (
            f"{station_train['timestamp'].min()} to {station_train['timestamp'].max()}"
            if not station_train.empty
            else "NO DATA"
        )
        test_daterange = (
            f"{station_test['timestamp'].min()} to {station_test['timestamp'].max()}"
            if not station_test.empty
            else "NO DATA"
        )

        has_gap = False
        if not station_train.empty:
            sorted_ts = station_train["timestamp"].sort_values()
        else:
            sorted_ts = pd.Series(dtype="datetime64[ns]")

        print(f"\n  Station: {station_id}")
        print(f"    Total rows:         {total}")
        print(f"    Train rows:         {train_n} ({train_pct:.1f}%)")
        print(f"    Validation rows:    {val_n}")
        print(f"    Test rows:          {test_n}")
        print(f"    Train date range:   {train_daterange}")
        print(f"    Test date range:    {test_daterange}")
        print(f"    Global split:       train ≤ {split_boundaries['train_end']}, "
              f"val ≤ {split_boundaries['validation_end']}")

        if total > 0:
            completion = features[features["station_id"] == station_id][TARGET_COLUMN].notna().mean() * 100
            print(f"    Target completeness: {completion:.1f}%")


def hypothesis_2(features, train, test):
    """Feature/target signal strength per station."""
    print("\n" + "=" * 80)
    print("HYPOTHESIS 2 — Feature/target signal strength per station")
    print("=" * 80)

    persistence_plot_cols = ["pm25_lag_24h", TARGET_COLUMN]
    stations_df = features[features["station_id"].isin(STATIONS)].copy()
    stations_df = stations_df.dropna(subset=[TARGET_COLUMN])

    print(f"\n  {'Station':<22} {'Test rows':<10} {'Target mean':<12} {'Target std':<12} "
          f"{'Target CV':<10} {'Persistence RMSE':<16} {'Reported RMSE':<16} {'Match':<8}")
    print(f"  {'-'*22} {'-'*10} {'-'*12} {'-'*12} {'-'*10} {'-'*16} {'-'*16} {'-'*8}")

    for station_id in STATIONS:
        test_data = test[test["station_id"] == station_id].copy()
        test_clean = test_data.dropna(subset=["pm25_lag_24h", TARGET_COLUMN])

        target_test = test_clean[TARGET_COLUMN]
        t_mean = target_test.mean()
        t_std = target_test.std()
        t_cv = t_std / t_mean if t_mean > 0 else 0.0
        if len(test_clean) > 0:
            persistence_preds = test_clean["pm25_lag_24h"].values
            actuals = test_clean[TARGET_COLUMN].values
            computed_rmse = float(np.sqrt(np.mean((actuals - persistence_preds) ** 2)))
        else:
            computed_rmse = float("nan")

        # Load reported persistence RMSE
        eval_path = Path(__file__).resolve().parents[2] / "ml/artifacts/multistation/evaluation_metrics.json"
        with eval_path.open() as f:
            eval_data = json.load(f)
        reported_rmse = eval_data["per_station"].get(station_id, {}).get("persistence_rmse", float("nan"))
        match = "OK" if abs(computed_rmse - reported_rmse) < 0.5 else "MISMATCH"
        print(f"  {station_id:<22} {len(test_clean):<10} {t_mean:<12.2f} {t_std:<12.2f} "
              f"{t_cv:<10.2f} {computed_rmse:<16.2f} {reported_rmse:<16.2f} {match:<8}")

    # Feature-target correlation per station
    print(f"\n  Per-station feature-target correlation with {TARGET_COLUMN}:")
    feature_cols_selected = [
        "pm25_lag_1h", "pm25_lag_3h", "pm25_lag_6h", "pm25_lag_12h", "pm25_lag_24h",
        "pm10_lag_1h", "pm10_lag_24h", "no2_lag_1h", "no2_lag_24h",
        "temperature_c", "relative_humidity", "rainfall_mm",
        "pm25_roll_mean_3h", "pm25_roll_mean_6h", "pm25_roll_mean_24h", "pm25_roll_std_24h",
        "hour_sin", "hour_cos",
    ]

    header = f"  {'Feature':<24}" + "".join(f"{s[-10:]:>10}" for s in STATIONS)
    print(header)
    print(f"  {'-'*24}" + "-" * 60)

    # Correlations computed on test-split data (matches the split used for RMSE evaluation).
    station_corr_data = {}
    for feature in feature_cols_selected:
        row = f"  {feature:<24}"
        for station_id in STATIONS:
            station_test = test[test["station_id"] == station_id].copy()
            sdata = station_test[[feature, TARGET_COLUMN]].dropna()
            if len(sdata) > 10:
                corr = sdata[feature].corr(sdata[TARGET_COLUMN])
                row += f"{corr:>10.3f}"
            else:
                row += f"{'N/A':>10}"
            if station_id not in station_corr_data:
                station_corr_data[station_id] = {}
            station_corr_data[station_id][feature] = corr if len(sdata) > 10 else float("nan")
        print(row)

    print(f"\n  Mean absolute feature-target correlation per station (test-split only):")
    for station_id in STATIONS:
        abs_vals = [abs(v) for v in station_corr_data[station_id].values() if not np.isnan(v)]
        mean_abs = np.mean(abs_vals) if abs_vals else 0.0
        print(f"    {station_id:<22} {mean_abs:.4f}")


def hypothesis_3(features):
    """One-hot station encoding feature importance."""
    print("\n" + "=" * 80)
    print("HYPOTHESIS 3 — One-hot station encoding is too weak a signal")
    print("=" * 80)

    model_path = Path(__file__).resolve().parents[2] / "ml/artifacts/multistation/lightgbm_pm25_24h.joblib"
    feature_cols_path = Path(__file__).resolve().parents[2] / "ml/artifacts/multistation/feature_columns.json"
    station_cols_path = Path(__file__).resolve().parents[2] / "ml/artifacts/multistation/station_feature_columns.json"

    if not model_path.exists():
        print("\n  Model file not found at", model_path)
        print("  Cannot extract feature importances.")
        return

    try:
        import joblib
        import lightgbm as lgb
    except ImportError:
        print("\n  LightGBM not available.")
        return

    model = joblib.load(model_path)
    with feature_cols_path.open() as f:
        feature_cols = json.load(f)
    with station_cols_path.open() as f:
        station_cols = json.load(f)
    all_cols = feature_cols + station_cols

    importances = model.feature_importances_
    if importances is None:
        print("\n  Model does not expose feature_importances_.")
        return

    sorted_idx = np.argsort(importances)[::-1]
    total_imp = importances.sum()

    print(f"\n  Total features: {len(all_cols)} ({len(feature_cols)} base + {len(station_cols)} station dummies)")
    print(f"  {'Rank':<6} {'Feature':<36} {'Importance':<12} {'Cum%':<8} {'Type'}")
    print(f"  {'-'*6} {'-'*36} {'-'*12} {'-'*8} {'-'*14}")

    cum = 0.0
    station_importances = {}
    for rank, idx in enumerate(sorted_idx, 1):
        name = all_cols[idx]
        imp = float(importances[idx])
        pct = imp / total_imp * 100
        cum += pct
        ftype = "station_dummy" if name.startswith("is_station_") else "base_feature"
        print(f"  {rank:<6} {name:<36} {imp:<12.0f} {cum:<8.1f} {ftype}")
        if ftype == "station_dummy":
            station_importances[name] = imp

    # Station dummy ranking
    print(f"\n  Station dummy feature importance ranking:")
    for name, imp in sorted(station_importances.items(), key=lambda x: x[1], reverse=True):
        rank = list(all_cols).index(name) + 1
        print(f"    {name:<36} importance={imp:<8.0f}  rank={rank}/{len(all_cols)}")

    station_mean_imp = np.mean(list(station_importances.values())) if station_importances else 0
    all_mean_imp = np.mean(importances)
    print(f"\n    Mean station dummy importance: {station_mean_imp:.1f}")
    print(f"    Mean overall feature importance: {all_mean_imp:.1f}")
    print(f"    Station dummies are {station_mean_imp / all_mean_imp:.2f}x the average feature.")


def hypothesis_4(features, train, test, training_feature_cols):
    """Synthesis — correlation of RMSE gap with other factors."""
    print("\n" + "=" * 80)
    print("HYPOTHESIS 4 — Synthesis: what correlates with the RMSE gap?")
    print("=" * 80)

    eval_path = Path(__file__).resolve().parents[2] / "ml/artifacts/multistation/evaluation_metrics.json"
    with eval_path.open() as f:
        eval_data = json.load(f)

    stations_df = features[features["station_id"].isin(STATIONS)].copy()

    print(f"\n  {'Station':<22} {'Test rows':<10} {'Target std':<12} {'Persist RMSE':<12} "
          f"{'LGBM RMSE':<12} {'RMSE gap':<12} {'Gap %':<10} {'Train rows':<12}")
    print(f"  {'-'*22} {'-'*10} {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*10} {'-'*12}")

    for station_id in STATIONS:
        per = eval_data["per_station"].get(station_id, {})
        persist_rmse = per.get("persistence_rmse", 0)
        lgbm_rmse = per.get("lightgbm_rmse", 0)
        gap = lgbm_rmse - persist_rmse
        gap_pct = per.get("rmse_improvement_percent", 0)
        test_rows = per.get("test_rows", 0)

        train_n = len(train[train["station_id"] == station_id])
        station_test = test[test["station_id"] == station_id]
        t_std = station_test[TARGET_COLUMN].dropna().std()

        print(f"  {station_id:<22} {test_rows:<10} {t_std:<12.2f} {persist_rmse:<12.2f} "
              f"{lgbm_rmse:<12.2f} {gap:<+12.2f} {gap_pct:<+10.1f} {train_n:<12}")

    print(f"\n  Note: Negative 'RMSE gap' / 'Gap %' means LightGBM is WORSE than persistence.")
    print(f"  Positive means LightGBM beats persistence.")


def main():
    print("LightGBM Underperformance Diagnostic")
    print("=" * 80)
    print(f"Analysis based on data in the repo as of {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")

    features, train, validation, test, training_feature_cols, project_root = load_data()

    print(f"Global split boundaries:")
    print(f"  Training:   {train['timestamp'].min()} -> {train['timestamp'].max()} ({len(train)} rows)")
    print(f"  Validation: {validation['timestamp'].min()} -> {validation['timestamp'].max()} ({len(validation)} rows)")
    print(f"  Test:       {test['timestamp'].min()} -> {test['timestamp'].max()} ({len(test)} rows)")
    print(f"  Total features: {len(training_feature_cols)} ({len([c for c in training_feature_cols if 'is_station_' not in c])} base + {len([c for c in training_feature_cols if 'is_station_' in c])} station dummies)")

    hypothesis_1(features, train, validation, test)
    hypothesis_2(features, train, test)
    hypothesis_3(features)
    hypothesis_4(features, train, test, training_feature_cols)

    print("\n" + "=" * 80)
    print("Diagnostic complete.")
    print("=" * 80)


if __name__ == "__main__":
    main()
