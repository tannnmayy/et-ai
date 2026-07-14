"""Citizen Mode API — neighbourhood matching for the citizen frontend."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.app.schemas.citizen import CitizenProfile, NeighbourhoodMatch
from backend.app.services.citizen_matching_service import (
    OfficeLocationUnresolvedError,
    match_neighbourhoods,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/citizen", tags=["citizen"])


@router.post(
    "/matches",
    response_model=list[NeighbourhoodMatch],
    summary="Rank neighbourhoods for a citizen profile",
    description=(
        "Returns a bare JSON array of NeighbourhoodMatch objects (not wrapped "
        "in an envelope), matching the citizen-mode frontend contract for "
        "POST /citizen/matches."
    ),
)
def citizen_matches(profile: CitizenProfile) -> list[NeighbourhoodMatch]:
    try:
        matches = match_neighbourhoods(profile)
    except OfficeLocationUnresolvedError as exc:
        # Honest failure: do not invent an office location.
        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not resolve officeLocation {profile.officeLocation!r} "
                f"to coordinates: {exc.message}. "
                "Try a known Bengaluru locality name (e.g. 'Indiranagar') "
                "or ensure Google Maps geocoding is configured."
            ),
        ) from exc
    except FileNotFoundError as exc:
        logger.exception("Citizen feature vectors missing")
        raise HTTPException(
            status_code=503,
            detail="Citizen Mode feature vectors are not available on this server.",
        ) from exc
    except Exception as exc:  # pragma: no cover — unexpected
        logger.exception("Citizen matching failed")
        raise HTTPException(status_code=500, detail=f"Matching failed: {exc}") from exc

    # Empty list is a valid, honest response (frontend has an empty-state UI).
    return matches
