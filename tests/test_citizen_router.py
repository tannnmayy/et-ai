"""API tests for POST /citizen/matches."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.citizen import NeighbourhoodFeatureVector, NeighbourhoodMatch
from backend.app.services.citizen_matching_service import OfficeLocationUnresolvedError

client = TestClient(app)

VALID_PROFILE = {
    "rentBudget": 45000,
    "familySize": 2,
    "healthConditions": ["none"],
    "officeLocation": "Indiranagar",
    "maxCommuteMinutes": 45,
    "priorities": ["low_aqi", "parks"],
}


def _sample_match(name: str = "Koramangala", rank: int = 1) -> NeighbourhoodMatch:
    return NeighbourhoodMatch(
        rank=rank,
        name=name,
        matchScorePercent=88.5,
        reasons=[
            "Rent fits your ₹45,000 budget (median ₹38,000)",
            "Good air quality here (PM2.5 ≈ 45 µg/m³)",
        ],
        featureVector=NeighbourhoodFeatureVector(
            aqi=45.0,
            aqiIsEstimated=False,
            avgRentForBudgetBHK=38000.0,
            rentIsEstimated=False,
            commuteMinutesToOffice=22.0,
            hospitalScore=60.0,
            schoolScore=60.0,
            parkScore=75.0,
            metroDistanceKm=None,
            noiseScore=40.0,
            constructionActivityScore=15.0,
        ),
    )


class TestCitizenRouter:
    @patch("backend.app.routers.citizen.match_neighbourhoods")
    def test_valid_profile_returns_bare_array(self, mock_match) -> None:
        mock_match.return_value = [
            _sample_match("Koramangala", 1),
            _sample_match("Indiranagar", 2),
        ]

        response = client.post("/citizen/matches", json=VALID_PROFILE)
        assert response.status_code == 200
        data = response.json()

        # Bare array — not {"matches": [...]}
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["rank"] == 1
        assert data[0]["name"] == "Koramangala"
        assert "matchScorePercent" in data[0]
        assert "reasons" in data[0]
        assert "featureVector" in data[0]
        fv = data[0]["featureVector"]
        assert "aqi" in fv
        assert "aqiIsEstimated" in fv
        assert "avgRentForBudgetBHK" in fv
        assert "rentIsEstimated" in fv
        assert "commuteMinutesToOffice" in fv
        assert "hospitalScore" in fv
        assert "schoolScore" in fv
        assert "parkScore" in fv
        assert "metroDistanceKm" in fv
        assert "noiseScore" in fv
        assert "constructionActivityScore" in fv

    @patch("backend.app.routers.citizen.match_neighbourhoods")
    def test_impossible_constraints_return_empty_array(self, mock_match) -> None:
        mock_match.return_value = []

        response = client.post(
            "/citizen/matches",
            json={
                **VALID_PROFILE,
                "rentBudget": 5000,
                "maxCommuteMinutes": 5,
            },
        )
        assert response.status_code == 200
        assert response.json() == []

    @patch("backend.app.routers.citizen.match_neighbourhoods")
    def test_unresolved_office_returns_422(self, mock_match) -> None:
        mock_match.side_effect = OfficeLocationUnresolvedError(
            "Could not resolve officeLocation"
        )

        response = client.post(
            "/citizen/matches",
            json={**VALID_PROFILE, "officeLocation": "zzzz_nowhere"},
        )
        assert response.status_code == 422
        assert "officeLocation" in response.json()["detail"]

    def test_invalid_profile_rejected(self) -> None:
        response = client.post(
            "/citizen/matches",
            json={
                "rentBudget": -1,
                "familySize": 0,
                "officeLocation": "",
                "maxCommuteMinutes": 45,
                "healthConditions": [],
                "priorities": [],
            },
        )
        assert response.status_code == 422
