from __future__ import annotations

import logging
from typing import Any

from backend.app.agents.llm_provider import (
    _CAUSAL_EXPLANATION_SYSTEM_PROMPT,
    _ENFORCEMENT_ACTION_SYSTEM_PROMPT,
    get_llm_provider,
)
from backend.app.config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "hi": {
        "top_source": "मुख्य स्रोत",
        "wind_based": "हवा आधारित विश्लेषण",
        "calm_based": "शांत मौसम अनुमान",
        "wind_speed": "हवा की गति",
        "direction": "दिशा",
        "kmh": "किमी/घंटा",
        "traffic": "यातायात",
        "industrial": "औद्योगिक",
        "construction": "निर्माण",
        "burning": "जलाना",
        "contributing_sources": "योगदान देने वाले स्रोत",
        "based_on": "पर आधारित",
        "nearby_contributors": "आस-पास के योगदानकर्ता",
        "fused_pm25": "अनुमानित PM2.5",
        "not_available": "उपलब्ध नहीं",
    },
    "kn": {
        "top_source": "ಪ್ರಮುಖ ಮೂಲ",
        "wind_based": "ಗಾಳಿ ಆಧಾರಿತ ವಿಶ್ಲೇಷಣೆ",
        "calm_based": "ಶಾಂತ ಹವಾಮಾನ ಅಂದಾಜು",
        "wind_speed": "ಗಾಳಿಯ ವೇಗ",
        "direction": "ದಿಕ್ಕು",
        "kmh": "ಕಿಮೀ/ಗಂ",
        "traffic": "ಸಂಚಾರ",
        "industrial": "ಕೈಗಾರಿಕಾ",
        "construction": "ನಿರ್ಮಾಣ",
        "burning": "ಸುಡುವಿಕೆ",
        "contributing_sources": "ಕೊಡುಗೆ ನೀಡುವ ಮೂಲಗಳು",
        "based_on": "ಆಧಾರಿತ",
        "nearby_contributors": "ಹತ್ತಿರದ ಕೊಡುಗೆದಾರರು",
        "fused_pm25": "ಅಂದಾಜು PM2.5",
        "not_available": "ಲಭ್ಯವಿಲ್ಲ",
    },
}


def _get_top_source(attribution: dict[str, float]) -> tuple[str, float]:
    return max(attribution.items(), key=lambda x: x[1])


def _get_top_sources(attribution: dict[str, float], n: int = 2) -> list[tuple[str, float]]:
    return sorted(attribution.items(), key=lambda x: -x[1])[:n]


_SOURCE_NAMES_EN: dict[str, str] = {
    "traffic": "traffic",
    "industrial": "industrial activity",
    "construction": "construction",
    "burning": "burning",
}

_SOURCE_NAMES_HI: dict[str, str] = {
    "traffic": "यातायात",
    "industrial": "औद्योगिक गतिविधि",
    "construction": "निर्माण कार्य",
    "burning": "जलाना",
}

_SOURCE_NAMES_KN: dict[str, str] = {
    "traffic": "ಸಂಚಾರ",
    "industrial": "ಕೈಗಾರಿಕಾ ಚಟುವಟಿಕೆ",
    "construction": "ನಿರ್ಮಾಣ",
    "burning": "ಸುಡುವಿಕೆ",
}

_SOURCE_NAMES: dict[str, dict[str, str]] = {
    "en": _SOURCE_NAMES_EN,
    "hi": _SOURCE_NAMES_HI,
    "kn": _SOURCE_NAMES_KN,
}


def _build_deterministic_explanation(hexagon_attribution: dict, language: str) -> str:
    source_attr = hexagon_attribution.get("source_attribution", {})
    method = hexagon_attribution.get("method", "unavailable")
    wind_used = hexagon_attribution.get("wind_used", {})
    fused = hexagon_attribution.get("fused_pm25")
    top_sources = _get_top_sources(source_attr, 2)
    names = _SOURCE_NAMES.get(language, _SOURCE_NAMES["en"])

    wind_method_str = _TRANSLATIONS.get(language, {}).get("wind_based", "Wind-based analysis")
    calm_method_str = _TRANSLATIONS.get(language, {}).get("calm_based", "Calm-weather estimate")
    method_label = wind_method_str if method == "wind_weighted" else calm_method_str

    lines: list[str] = []

    if language == "en":
        if top_sources:
            parts = [f"{names.get(s, s)} ({pct*100:.0f}%)" for s, pct in top_sources if pct > 0]
            if parts:
                lines.append(f"Top sources: {' and '.join(parts)}.")
        lines.append(f"Attribution method: {method_label}.")
        ws = wind_used.get("speed_kmh")
        if ws is not None:
            lines.append(f"Wind speed: {ws} km/h.")
        if fused is not None:
            lines.append(f"Estimated PM2.5: {fused} µg/m³.")
    else:
        t = _TRANSLATIONS.get(language, {})
        top_label = t.get("top_source", "Top source")
        if top_sources:
            parts = [f"{names.get(s, s)} ({pct*100:.0f}%)" for s, pct in top_sources if pct > 0]
            if parts:
                lines.append(f"{top_label}: {' '.join(parts)}.")
        lines.append(f"{t.get('based_on', 'Based on')}: {method_label}.")
        ws = wind_used.get("speed_kmh")
        if ws is not None:
            lines.append(f"{t.get('wind_speed', 'Wind speed')}: {ws} {t.get('kmh', 'km/h')}.")
        if fused is not None:
            lines.append(f"{t.get('fused_pm25', 'Estimated PM2.5')}: {fused} µg/m³.")

    return " ".join(lines)


def generate_causal_explanation(
    hexagon_attribution: dict,
    language: str = "en",
) -> dict[str, Any]:
    if language not in SUPPORTED_LANGUAGES:
        language = "en"

    source_attr = hexagon_attribution.get("source_attribution", {})
    method = hexagon_attribution.get("method", "unavailable")
    top_source_name, top_source_pct = _get_top_source(source_attr) if source_attr else ("unknown", 0.0)
    top_sources = _get_top_sources(source_attr, 2)

    names = _SOURCE_NAMES.get(language, _SOURCE_NAMES["en"])
    top_source_label = names.get(top_source_name, top_source_name)

    llm = get_llm_provider()

    if llm.is_available:
        prompt = (
            f"Explain the pollution sources at this location in {language.upper()}.\n\n"
            f"Source attribution breakdown:\n"
            f"  Traffic: {source_attr.get('traffic', 0)*100:.1f}%\n"
            f"  Industrial: {source_attr.get('industrial', 0)*100:.1f}%\n"
            f"  Construction: {source_attr.get('construction', 0)*100:.1f}%\n"
            f"  Burning: {source_attr.get('burning', 0)*100:.1f}%\n"
            f"Attribution method: {method}\n"
            f"Wind direction: {hexagon_attribution.get('wind_used', {}).get('direction_deg')}°\n"
            f"Wind speed: {hexagon_attribution.get('wind_used', {}).get('speed_kmh')} km/h\n"
            f"Contributing source hexagons: {hexagon_attribution.get('source_hexagons_contributing')}\n"
            f"Max source distance: {hexagon_attribution.get('max_distance_m')} m\n"
            f"Fused PM2.5 estimate: {hexagon_attribution.get('fused_pm25')} µg/m³\n"
            f"Baseline PM2.5: {hexagon_attribution.get('baseline_pm25')} µg/m³\n"
            f"Nearest station: {hexagon_attribution.get('nearest_station_id')} ({hexagon_attribution.get('nearest_station_distance_m')} m away)\n\n"
            f"Write your response in {language.upper()}. "
            f"Focus on the top sources ({top_source_label} at {top_source_pct*100:.0f}%) and the wind conditions. "
            f"Keep it to 3-5 sentences. Do not add information not present in the data."
        )
        explanation = llm.summarize(
            prompt, {"source_attribution": source_attr},
            system_prompt=_CAUSAL_EXPLANATION_SYSTEM_PROMPT,
        )
        if explanation:
            return {
                "explanation": explanation,
                "language": language,
                "generated_by": "llm",
                "wind_method": method,
            }

    fallback = _build_deterministic_explanation(hexagon_attribution, language)
    return {
        "explanation": fallback,
        "language": language,
        "generated_by": "template",
        "wind_method": method,
    }


_ACTION_TEMPLATES: dict[str, str] = {
    "traffic": "Coordinate with traffic police for congestion management and vehicle emissions checks during peak hours in this zone.",
    "industrial": "Inspect nearby industrial facilities for emissions compliance and verify stack emission controls are operational.",
    "construction": "Dispatch an inspector to verify dust suppression compliance (water spraying, covers, barriers) at active construction sites in this zone.",
    "burning": "Patrol for open waste burning and biomass combustion in residential areas; issue fines for violations under air quality regulations.",
}


def generate_enforcement_action_guidance(
    scoring_breakdown: dict[str, float] | None = None,
    source_attribution: dict[str, float] | None = None,
    fused_pm25: float | None = None,
    top_source: str | None = None,
) -> dict[str, Any]:
    """Generate an actionable enforcement recommendation for a ranked hexagon."""
    if not source_attribution:
        return {
            "text": "No source attribution available for this hexagon.",
            "generated_by": "unavailable",
        }

    source_attr = source_attribution
    method = "vectorised_feature_proxy"
    top_source_name, top_source_pct = _get_top_source(source_attr) if source_attr else ("unknown", 0.0)
    names = _SOURCE_NAMES["en"]
    top_source_label = names.get(top_source_name, top_source_name)

    llm = get_llm_provider()
    if llm.is_available:
        prompt = (
            f"Generate an actionable enforcement recommendation for a Bengaluru hexagon.\n\n"
            f"Top source: {top_source_label} at {top_source_pct * 100:.0f}%\n"
            f"Source breakdown:\n"
            f"  Traffic: {source_attr.get('traffic', 0) * 100:.1f}%\n"
            f"  Industrial: {source_attr.get('industrial', 0) * 100:.1f}%\n"
            f"  Construction: {source_attr.get('construction', 0) * 100:.1f}%\n"
            f"  Burning: {source_attr.get('burning', 0) * 100:.1f}%\n"
            f"Estimated PM2.5: {fused_pm25} µg/m³\n"
        )
        if scoring_breakdown:
            prompt += (
                f"Exposure weight: {scoring_breakdown.get('exposure_weight', 0):.2f}\n"
                f"Attributable magnitude: {scoring_breakdown.get('attributable_magnitude', 0):.2f}\n"
                f"Actionability weight: {scoring_breakdown.get('actionability_weight', 0):.2f}\n"
            )
        explanation = llm.summarize(
            prompt,
            {"source_attribution": source_attr, "scoring_breakdown": scoring_breakdown or {}},
            system_prompt=_ENFORCEMENT_ACTION_SYSTEM_PROMPT,
        )
        if explanation:
            return {
                "text": explanation,
                "generated_by": "llm",
            }

    template = _ACTION_TEMPLATES.get(top_source_name,
        f"Inspect the dominant source category '{top_source_label}' in this zone and verify compliance with applicable regulations.")
    pct_detail = f" ({top_source_pct * 100:.0f}% of attributed PM2.5)"
    pm25_detail = f" Estimated PM2.5: {fused_pm25} µg/m³." if fused_pm25 is not None else ""
    return {
        "text": f"Priority source: {top_source_label}{pct_detail}. {template}{pm25_detail}",
        "generated_by": "template",
    }
