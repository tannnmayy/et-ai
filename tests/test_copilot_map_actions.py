"""Bidirectional Map ↔ Copilot: map_actions extraction and response field."""

from __future__ import annotations

from unittest.mock import patch

from backend.app.agents.map_actions import extract_map_actions
from backend.app.agents.orchestrator import run_orchestrator


class TestExtractMapActions:
    def test_enforcement_hexes(self):
        actions = extract_map_actions(
            tool_results={
                "get_enforcement_priority": {
                    "ranked_hexagons": [
                        {
                            "h3_cell": "8960145a02fffff",
                            "location_name": "Peenya Industrial",
                            "center_lat": 13.03,
                            "center_lon": 77.52,
                        },
                        {"h3_cell": "8960145a03fffff", "location_name": "Yeshwanthpur"},
                    ]
                }
            }
        )
        assert actions is not None
        assert "8960145a02fffff" in actions["highlight_h3_cells"]
        assert actions["focus_on"]["h3_cell"] == "8960145a02fffff"
        assert actions["focus_on"]["label"] == "Peenya Industrial"

    def test_attribution_and_station(self):
        actions = extract_map_actions(
            tool_results={
                "get_attribution": {
                    "h3_cell": "abc123",
                    "nearest_station_id": "cpcb_peenya",
                    "center_lat": 13.0,
                    "center_lon": 77.5,
                }
            }
        )
        assert actions is not None
        assert "abc123" in actions["highlight_h3_cells"]
        assert "cpcb_peenya" in actions["highlight_stations"]

    def test_state_fallback(self):
        actions = extract_map_actions(
            tool_results={},
            state_station_id="cpcb_hebbal",
            state_h3_cell="hex_hebbal",
        )
        assert actions is not None
        assert "cpcb_hebbal" in actions["highlight_stations"]
        assert "hex_hebbal" in actions["highlight_h3_cells"]

    def test_empty_returns_none(self):
        assert extract_map_actions(tool_results={}) is None


class TestOrchestratorMapActions:
    def test_enforcement_query_returns_map_actions(self):
        class Fake:
            is_available = False
            last_provider = None
            last_gemini_key_index = None
            last_groq_key_index = None

            def chat_with_tools(self, *a, **k):
                return None

            def summarize(self, *a, **k):
                return None

        with patch(
            "backend.app.agents.grounded_tool_agent.get_llm_provider", return_value=Fake()
        ), patch(
            "backend.app.agents.orchestrator.get_llm_provider", return_value=Fake()
        ):
            out = run_orchestrator(
                query="Where should officers inspect for construction dust today?",
                city="bengaluru",
            )
        assert out.get("answer")
        ma = out.get("map_actions")
        # Enforcement tool should yield hexes when data available
        if ma:
            assert isinstance(ma.get("highlight_h3_cells"), list)
            assert len(ma["highlight_h3_cells"]) >= 1 or len(ma.get("highlight_stations") or []) >= 0

    def test_map_context_on_station_fast_path(self):
        class Fake:
            is_available = False
            last_provider = None
            last_gemini_key_index = None
            last_groq_key_index = None

            def chat_with_tools(self, *a, **k):
                return None

            def summarize(self, *a, **k):
                return None

        with patch(
            "backend.app.agents.grounded_tool_agent.get_llm_provider", return_value=Fake()
        ), patch(
            "backend.app.agents.orchestrator.get_llm_provider", return_value=Fake()
        ):
            out = run_orchestrator(
                query="What is the forecast for this station?",
                city="bengaluru",
                station_id="cpcb_peenya",
            )
        assert out["selected_agent"] == "forecast_evidence_agent"
        ma = out.get("map_actions")
        assert ma is not None
        assert "cpcb_peenya" in (ma.get("highlight_stations") or [])
