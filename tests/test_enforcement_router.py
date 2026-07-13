from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


class TestEnforcementRouter:
    @patch("backend.app.routers.enforcement.compute_enforcement_priorities")
    def test_priority_bengaluru_returns_200_with_top_k(self, mock_compute):
        mock_compute.return_value = {
            "city": "Bengaluru",
            "computed_at": "2025-01-01T00:00:00+00:00",
            "total_hexagons": 100,
            "top_k": 5,
            "ranked_hexagons": [
                {
                    "h3_cell": f"hex_{i}",
                    "priority_score": round(1.0 - i * 0.1, 4),
                    "rank": i + 1,
                    "scoring_breakdown": {
                        "exposure_weight": 0.8,
                        "attributable_magnitude": 0.7,
                        "actionability_weight": 0.9,
                    },
                    "fused_pm25": 120.0 - i * 5,
                    "source_attribution": {
                        "traffic": 0.3,
                        "industrial": 0.4,
                        "construction": 0.2,
                        "burning": 0.1,
                    },
                    "method": "wind_weighted",
                    "explanation": {
                        "text": f"High industrial contribution. PM2.5 {120.0 - i * 5} µg/m³.",
                        "generated_by": "rule",
                    },
                }
                for i in range(5)
            ],
        }

        response = client.get("/enforcement/priority/bengaluru?top_k=5")
        assert response.status_code == 200
        data = response.json()
        assert "ranked_hexagons" in data
        assert len(data["ranked_hexagons"]) == 5
        assert data["top_k"] == 5
        assert data["city"] == "Bengaluru"

    @patch("backend.app.routers.enforcement.compute_enforcement_priorities")
    def test_priority_unknown_city_returns_503(self, mock_compute):
        mock_compute.return_value = {"error": "Unsupported city: 'notacity'"}

        response = client.get("/enforcement/priority/notacity")
        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
