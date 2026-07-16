"""City Insights API — defensible, data-grounded narrative pack for the Insights tab."""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.services.insights_service import get_city_insights

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get(
    "/city/{city}",
    summary="High-signal city insights pack for the Insights page",
    description="Returns six data-grounded insights (rush-hour source flip, sensor gaps, "
    "predictability map, targeted enforcement concentration, rent vs air, before/after). "
    "Numbers are computed from live services and evaluation artifacts — not placeholders.",
)
def city_insights(
    city: str = "bengaluru",
    refresh: bool = Query(default=False, description="Bypass short in-process cache"),
) -> dict:
    # City currently only bengaluru is fully instrumented
    return get_city_insights(force_refresh=refresh)
