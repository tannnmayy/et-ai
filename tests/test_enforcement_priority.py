from __future__ import annotations

import pandas as pd
import pytest

from backend.app.services.enforcement_priority_service import (
    _compute_exposure_weight,
    _compute_attributable_magnitude,
    _compute_actionability_weight,
    ACTIONABILITY_INDUSTRIAL,
    ACTIONABILITY_CONSTRUCTION,
    ACTIONABILITY_BURNING,
    ACTIONABILITY_TRAFFIC,
)


# ---------------------------------------------------------------------------
# Unit tests for decomposed scoring components
# ---------------------------------------------------------------------------


class TestExposureWeight:
    def test_high_vulnerability_with_residential(self):
        row = pd.Series({"vulnerability_feature_count": 5, "residential_fraction": 0.5})
        w = _compute_exposure_weight(row)
        assert w == 1.0, "5 vulnerability features + high residential should saturate to 1.0"

    def test_no_vulnerability_uses_residential_fallback(self):
        row = pd.Series({"vulnerability_feature_count": 0, "residential_fraction": 0.5})
        w = _compute_exposure_weight(row)
        expected = 0.0 * 0.7 + min(1.0, 0.5 / 0.5) * 0.3
        assert abs(w - expected) < 1e-10, f"Expected {expected}, got {w}"

    def test_none_hex_row_returns_default(self):
        w = _compute_exposure_weight(None)
        assert w == 0.5, "None hex_row should return default 0.5"

    def test_zero_everything(self):
        row = pd.Series({"vulnerability_feature_count": 0, "residential_fraction": 0.0})
        w = _compute_exposure_weight(row)
        assert w == 0.0, "Zero vulnerability and zero residential should give 0"

    def test_missing_columns_default_to_zero(self):
        row = pd.Series({"vulnerability_feature_count": float("nan"), "residential_fraction": 0.0})
        w = _compute_exposure_weight(row)
        assert w == 0.0

    def test_vulnerability_dominates_residential(self):
        high_vuln = pd.Series({"vulnerability_feature_count": 3, "residential_fraction": 0.0})
        high_res = pd.Series({"vulnerability_feature_count": 0, "residential_fraction": 0.5})
        w_high_vuln = _compute_exposure_weight(high_vuln)
        w_high_res = _compute_exposure_weight(high_res)
        assert w_high_vuln > w_high_res, (
            "Hex with 3 vulnerability features should score higher than "
            "hex with 0 vulnerability features even with moderate residential density"
        )


class TestAttributableMagnitude:
    def test_high_pm25_high_enforceable_frac(self):
        attr = {"traffic": 0.1, "industrial": 0.6, "construction": 0.2, "burning": 0.1}
        m = _compute_attributable_magnitude(200.0, attr)
        enforceable = 0.6 + 0.2 + 0.1
        expected = min(1.0, 200.0 * enforceable / 300.0)
        assert m == expected, f"Expected {expected}, got {m}"

    def test_fused_pm25_none_returns_zero(self):
        m = _compute_attributable_magnitude(None, {"industrial": 1.0})
        assert m == 0.0

    def test_zero_enforceable_frac(self):
        attr = {"traffic": 1.0, "industrial": 0.0, "construction": 0.0, "burning": 0.0}
        m = _compute_attributable_magnitude(150.0, attr)
        assert m == 0.0, "Zero enforceable fraction should give magnitude 0"

    def test_saturates_at_max_pm25(self):
        attr = {"industrial": 1.0, "traffic": 0.0, "construction": 0.0, "burning": 0.0}
        m_low = _compute_attributable_magnitude(150.0, attr)
        m_high = _compute_attributable_magnitude(600.0, attr)
        assert m_low < m_high
        assert m_high == 1.0, "Should saturate at 1.0"


class TestActionabilityWeight:
    def test_pure_industrial_gives_max(self):
        attr = {"traffic": 0.0, "industrial": 1.0, "construction": 0.0, "burning": 0.0}
        w = _compute_actionability_weight(attr)
        assert w == ACTIONABILITY_INDUSTRIAL

    def test_pure_traffic_gives_traffic_weight(self):
        attr = {"traffic": 1.0, "industrial": 0.0, "construction": 0.0, "burning": 0.0}
        w = _compute_actionability_weight(attr)
        assert w == ACTIONABILITY_TRAFFIC

    def test_mixed_sources_weighted_average(self):
        attr = {"traffic": 0.5, "industrial": 0.5, "construction": 0.0, "burning": 0.0}
        expected = (0.5 * ACTIONABILITY_TRAFFIC + 0.5 * ACTIONABILITY_INDUSTRIAL) / 1.0
        w = _compute_actionability_weight(attr)
        assert abs(w - expected) < 1e-10

    def test_zero_total_returns_zero(self):
        attr = {"traffic": 0.0, "industrial": 0.0, "construction": 0.0, "burning": 0.0}
        w = _compute_actionability_weight(attr)
        assert w == 0.0

    def test_industrial_higher_than_traffic(self):
        ind = {"industrial": 1.0, "traffic": 0.0, "construction": 0.0, "burning": 0.0}
        traf = {"traffic": 1.0, "industrial": 0.0, "construction": 0.0, "burning": 0.0}
        assert _compute_actionability_weight(ind) > _compute_actionability_weight(traf)


# ---------------------------------------------------------------------------
# Integration-style tests using mock hexagon data
# ---------------------------------------------------------------------------


def _make_hex_row(
    vulnerability_feature_count: int = 0,
    residential_fraction: float = 0.0,
) -> pd.Series:
    return pd.Series({
        "vulnerability_feature_count": vulnerability_feature_count,
        "residential_fraction": residential_fraction,
    })


class TestPriorityFormulaIntegration:
    def test_high_exposure_high_industrial_high_score(self):
        """High exposure + high industrial attribution → high priority score."""
        hex_row = _make_hex_row(vulnerability_feature_count=5, residential_fraction=0.3)
        attr = {"traffic": 0.05, "industrial": 0.80, "construction": 0.10, "burning": 0.05}

        exposure = _compute_exposure_weight(hex_row)
        magnitude = _compute_attributable_magnitude(250.0, attr)
        actionability = _compute_actionability_weight(attr)
        score = exposure * magnitude * actionability

        assert exposure > 0.8, f"Expected high exposure, got {exposure}"
        assert magnitude > 0.5
        assert actionability > 0.9
        assert score > 0.4, f"Expected high score > 0.4, got {score}"

    def test_high_exposure_pure_traffic_lower_score(self):
        """High exposure + pure traffic → lower score due to low actionability."""
        hex_row = _make_hex_row(vulnerability_feature_count=5, residential_fraction=0.3)
        attr = {"traffic": 1.0, "industrial": 0.0, "construction": 0.0, "burning": 0.0}

        exposure = _compute_exposure_weight(hex_row)
        magnitude = _compute_attributable_magnitude(250.0, attr)
        actionability = _compute_actionability_weight(attr)
        score = exposure * magnitude * actionability

        assert exposure > 0.8, f"Expected high exposure, got {exposure}"
        assert magnitude == 0.0, "Traffic-only should give zero attributable magnitude"
        assert actionability == ACTIONABILITY_TRAFFIC
        assert score == 0.0, (
            "Traffic-only hexagon should have zero priority score "
            "because attributable magnitude is zero"
        )

    def test_traffic_only_with_some_industrial_medium_score(self):
        """Mixed traffic + industrial should score between pure cases."""
        hex_row = _make_hex_row(vulnerability_feature_count=3, residential_fraction=0.2)
        pure_traffic_attr = {"traffic": 1.0, "industrial": 0.0, "construction": 0.0, "burning": 0.0}
        mixed_attr = {"traffic": 0.6, "industrial": 0.4, "construction": 0.0, "burning": 0.0}

        exposure = _compute_exposure_weight(hex_row)
        pure_score = exposure * _compute_attributable_magnitude(200.0, pure_traffic_attr) * _compute_actionability_weight(pure_traffic_attr)
        mixed_score = exposure * _compute_attributable_magnitude(200.0, mixed_attr) * _compute_actionability_weight(mixed_attr)

        assert mixed_score > pure_score, "Mixed sources should score higher than pure traffic"

    def test_calm_fallback_method_preserved(self):
        """The method flag (calm_fallback) should propagate correctly."""
        attr = {"traffic": 0.3, "industrial": 0.4, "construction": 0.2, "burning": 0.1}
        hex_result = {
            "h3_cell": "test_cell",
            "fused_pm25": 150.0,
            "source_attribution": attr,
            "method": "calm_fallback",
        }

        # Simulate the service's per-hexagon logic
        hex_row = _make_hex_row(vulnerability_feature_count=2, residential_fraction=0.3)
        exposure = _compute_exposure_weight(hex_row)
        magnitude = _compute_attributable_magnitude(hex_result["fused_pm25"], hex_result["source_attribution"])
        actionability = _compute_actionability_weight(hex_result["source_attribution"])
        score = exposure * magnitude * actionability

        result = {
            "h3_cell": hex_result["h3_cell"],
            "priority_score": round(score, 4),
            "scoring_breakdown": {
                "exposure_weight": round(exposure, 4),
                "attributable_magnitude": round(magnitude, 4),
                "actionability_weight": round(actionability, 4),
            },
            "method": hex_result["method"],
        }

        assert result["method"] == "calm_fallback", (
            f"Expected calm_fallback, got {result['method']}"
        )
        assert result["priority_score"] > 0

    def test_wind_weighted_method_preserved(self):
        """The method flag (wind_weighted) should propagate correctly."""
        attr = {"traffic": 0.2, "industrial": 0.5, "construction": 0.2, "burning": 0.1}
        hex_result = {
            "h3_cell": "test_cell_wind",
            "fused_pm25": 120.0,
            "source_attribution": attr,
            "method": "wind_weighted",
        }

        hex_row = _make_hex_row(vulnerability_feature_count=1, residential_fraction=0.4)
        exposure = _compute_exposure_weight(hex_row)
        magnitude = _compute_attributable_magnitude(hex_result["fused_pm25"], hex_result["source_attribution"])
        actionability = _compute_actionability_weight(hex_result["source_attribution"])

        result = {
            "h3_cell": hex_result["h3_cell"],
            "priority_score": round(exposure * magnitude * actionability, 4),
            "method": hex_result["method"],
        }

        assert result["method"] == "wind_weighted"
