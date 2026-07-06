from __future__ import annotations

import pytest

from backend.app.config import INVESTIGATION_DISCLAIMER
from backend.app.services.inspection_priority_service import get_inspection_priorities
from backend.app.services.artifact_adapter import UnsupportedCityError


class TestGetInspectionPriorities:
    def test_returns_ranked_stations(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=5)
        assert result["city"] == "Bengaluru"
        assert result["total_stations"] == 6
        assert len(result["ranked_stations"]) == 5

    def test_top_k_behavior(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=3)
        assert len(result["ranked_stations"]) == 3
        assert result["top_k"] == 3

    def test_ranked_stations_sorted(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        scores = [s["priority_score"] for s in result["ranked_stations"]]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_sequential(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        ranks = [s["rank"] for s in result["ranked_stations"]]
        assert ranks == list(range(1, 7))

    def test_priority_score_range(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            assert 0 <= s["priority_score"] <= 100

    def test_valid_priority_levels(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        valid_levels = {"Critical", "High", "Moderate", "Watch"}
        for s in result["ranked_stations"]:
            assert s["priority_level"] in valid_levels

    def test_investigation_disclaimer_present(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            assert "investigation_disclaimer" in s
            assert s["investigation_disclaimer"] == INVESTIGATION_DISCLAIMER

    def test_investigation_disclaimer_not_causal(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            assert "not proof" in s["investigation_disclaimer"]

    def test_scoring_breakdown_present(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            bd = s["scoring_breakdown"]
            assert "forecast_severity" in bd
            assert "worsening" in bd
            assert "recent_elevated_pm25" in bd
            assert "confidence_adjustment" in bd
            assert "quality_adjustment" in bd

    def test_recommended_inspection_focus(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            assert len(s["recommended_inspection_focus"]) > 0

    def test_peenya_industrial_focus(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        peenya = [s for s in result["ranked_stations"] if s["station_id"] == "cpcb_peenya"][0]
        assert "industrial" in peenya["recommended_inspection_focus"].lower()

    def test_silkboard_traffic_focus(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        silk = [s for s in result["ranked_stations"] if s["station_id"] == "cpcb_silkboard"][0]
        assert "traffic" in silk["recommended_inspection_focus"].lower()

    def test_rationale_present(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            assert len(s["rationale"]) > 0

    def test_caveats_contain_disclaimer(self) -> None:
        result = get_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            assert any(INVESTIGATION_DISCLAIMER in c for c in s["caveats"])

    def test_unsupported_city(self) -> None:
        with pytest.raises(UnsupportedCityError):
            get_inspection_priorities("delhi")
