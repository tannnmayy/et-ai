"""Extract structured Map actions from Copilot tool results / state.

The frontend Map page consumes these to highlight hexes/stations and optional focus.
"""

from __future__ import annotations

from typing import Any


def _add_unique(seq: list[str], value: str | None, *, limit: int = 12) -> None:
    if not value:
        return
    v = str(value).strip()
    if not v or v in seq:
        return
    if len(seq) >= limit:
        return
    seq.append(v)


def extract_map_actions(
    *,
    tool_results: dict[str, Any] | None,
    state_station_id: str = "",
    state_h3_cell: str | None = None,
    structured_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build map_actions from successful tool payloads.

    Returns None when nothing useful to highlight (keeps responses lean).
    """
    highlight_h3: list[str] = []
    highlight_stations: list[str] = []
    focus: dict[str, Any] | None = None

    results = tool_results or {}
    if not results and isinstance(structured_data, dict):
        results = structured_data.get("tool_results") or {}

    for name, payload in results.items():
        if not isinstance(payload, dict) or payload.get("_tool_error"):
            continue

        # Enforcement priorities → top hexes
        if name in ("get_enforcement_priority", "tool_get_enforcement_priority"):
            ranked = payload.get("ranked_hexagons") or payload.get("hexagons") or []
            for h in ranked[:8]:
                if not isinstance(h, dict):
                    continue
                cell = h.get("h3_cell") or h.get("id") or h.get("hex_id")
                _add_unique(highlight_h3, cell)
                if focus is None and cell:
                    focus = {
                        "h3_cell": str(cell),
                        "label": h.get("location_name") or h.get("name"),
                        "lat": h.get("center_lat") or h.get("lat"),
                        "lng": h.get("center_lon") or h.get("lng") or h.get("lon"),
                    }

        # Attribution / causal / what-if single location
        if name in (
            "get_attribution",
            "get_causal_explanation",
            "run_whatif_scenario",
            "tool_get_attribution",
            "tool_get_causal_explanation",
            "tool_run_whatif_scenario",
        ):
            cell = payload.get("h3_cell")
            _add_unique(highlight_h3, cell)
            sid = payload.get("station_id") or payload.get("nearest_station_id")
            _add_unique(highlight_stations, sid)
            if cell or sid:
                focus = focus or {
                    "h3_cell": str(cell) if cell else None,
                    "station_id": str(sid) if sid else None,
                    "label": payload.get("location_label") or payload.get("location_name"),
                    "lat": payload.get("center_lat") or payload.get("lat"),
                    "lng": payload.get("center_lon") or payload.get("lon") or payload.get("lng"),
                }

        # Resolve location
        if name in ("resolve_location", "tool_resolve_location"):
            cell = payload.get("h3_cell") or payload.get("h3")
            _add_unique(highlight_h3, cell)
            sid = payload.get("station_id") or payload.get("nearest_station_id")
            _add_unique(highlight_stations, sid)
            if cell or sid:
                focus = focus or {
                    "h3_cell": str(cell) if cell else None,
                    "station_id": str(sid) if sid else None,
                    "label": (
                        payload.get("resolved_name")
                        or payload.get("display_name")
                        or payload.get("locality")
                        or payload.get("label")
                    ),
                    "lat": payload.get("latitude") or payload.get("lat"),
                    "lng": payload.get("longitude") or payload.get("lon") or payload.get("lng"),
                }

        # Forecast / confidence → station
        if name in (
            "get_forecast",
            "get_forecast_confidence",
            "tool_get_forecast_evidence",
            "tool_get_forecast_confidence",
        ):
            sid = payload.get("station_id")
            _add_unique(highlight_stations, sid)
            if sid and focus is None:
                focus = {
                    "station_id": str(sid),
                    "label": payload.get("station_name") or sid,
                }

    # Fall back to client / resolved state context
    _add_unique(highlight_stations, state_station_id or None)
    _add_unique(highlight_h3, state_h3_cell)

    if not highlight_h3 and not highlight_stations:
        return None

    if focus is None:
        if state_h3_cell:
            focus = {"h3_cell": state_h3_cell, "station_id": state_station_id or None}
        elif state_station_id:
            focus = {"station_id": state_station_id}

    # Clean focus nulls
    if focus:
        focus = {k: v for k, v in focus.items() if v is not None and v != ""}

    return {
        "highlight_h3_cells": highlight_h3,
        "highlight_stations": highlight_stations,
        "focus_on": focus or None,
    }
