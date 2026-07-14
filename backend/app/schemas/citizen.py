"""Pydantic schemas for Citizen Mode — mirrors the frontend TypeScript contract.

Field names are camelCase to match citizen mode frontend/src/types/citizen.ts
exactly (axios posts/receives these keys as-is).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


HealthCondition = Literal["respiratory", "elderly", "young_children", "none"]
CitizenPriority = Literal["metro", "schools", "hospitals", "parks", "low_aqi", "low_noise"]


class CitizenProfile(BaseModel):
    rentBudget: float = Field(..., gt=0, description="Monthly rent budget in INR")
    familySize: int = Field(..., ge=1, le=20, description="Household size")
    healthConditions: list[HealthCondition] = Field(default_factory=lambda: ["none"])
    officeLocation: str = Field(..., min_length=1, description="Free-text office location")
    maxCommuteMinutes: int = Field(..., ge=5, le=180, description="Max one-way commute minutes")
    priorities: list[CitizenPriority] = Field(default_factory=list)


class NeighbourhoodFeatureVector(BaseModel):
    aqi: float
    aqiIsEstimated: bool
    avgRentForBudgetBHK: float
    rentIsEstimated: bool
    commuteMinutesToOffice: float
    hospitalScore: float
    schoolScore: float
    parkScore: float
    # null when metro OSM data is unavailable (known limitation).
    metroDistanceKm: float | None = None
    noiseScore: float
    constructionActivityScore: float


class NeighbourhoodMatch(BaseModel):
    rank: int
    name: str
    matchScorePercent: float
    reasons: list[str]
    featureVector: NeighbourhoodFeatureVector
