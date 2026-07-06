from __future__ import annotations

from typing import Any

from backend.app.config import INVESTIGATION_DISCLAIMER, MEDICAL_DISCLAIMER


def render_station_explanation(data: dict[str, Any]) -> str:
    station = data.get("station_name", data.get("station_id", "Unknown"))
    pm25 = data.get("predicted_pm25", "N/A")
    risk = data.get("risk_category", "Unknown")
    engine = data.get("forecast_engine", "Unknown")
    method = data.get("explanation_method", "Unknown")
    change_dir = data.get("expected_change_direction", "unavailable")
    change_val = data.get("expected_change_pm25")
    confidence = data.get("confidence", {})
    conf_level = confidence.get("confidence_level", None) if confidence else None

    lines = [
        f"Station: {station}",
        f"Forecast PM2.5: {pm25} &#181;g/m\u00B3 ({risk})",
        f"Forecast engine: {engine}",
        f"Explanation method: {method}",
    ]

    if change_val is not None:
        sign = "+" if change_val > 0 else ""
        lines.append(f"Expected change: {sign}{change_val:.1f} &#181;g/m\u00B3 ({change_dir})")

    if conf_level:
        lines.append(f"Forecast confidence: {conf_level}")

    caveats = data.get("caveats", [])
    if caveats:
        lines.append(f"Caveats: {'; '.join(caveats)}")

    if data.get("data_quality_note"):
        lines.append(f"Data quality: {data['data_quality_note']}")

    if data.get("model_validation_summary"):
        lines.append(f"Validation: {data['model_validation_summary']}")

    lines.append("This explanation is based on station data and model evaluation. It does not identify specific pollution sources.")
    return "\n".join(lines)


def render_confidence_summary(data: dict[str, Any]) -> str:
    station = data.get("station_name", data.get("station_id", "Unknown"))
    level = data.get("confidence_level", "Unavailable")
    score = data.get("confidence_score")
    engine = data.get("selected_engine", "Unknown")
    quality = data.get("quality_classification", "Unknown")
    age = data.get("latest_observation_age_hours")
    completeness = data.get("recent_pm25_completeness_percent")

    lines = [
        f"Station: {station}",
        f"Confidence level: {level}",
    ]

    if score is not None:
        lines.append(f"Confidence score: {score}/100")

    lines.append(f"Selected engine: {engine}")
    lines.append(f"Data quality: {quality}")

    if age is not None:
        lines.append(f"Latest observation: {age:.1f}h ago")
    if completeness is not None:
        lines.append(f"Recent PM2.5 completeness: {completeness:.1f}%")

    reasons = data.get("reasons", [])
    if reasons:
        lines.append(f"Notes: {'; '.join(reasons)}")

    return "\n".join(lines)


def render_inspection_plan(data: dict[str, Any]) -> str:
    city = data.get("city", "Bengaluru")
    ranked = data.get("ranked_stations", [])
    disclaimer = INVESTIGATION_DISCLAIMER

    lines = [
        f"Inspection Priority Plan for {city}",
        f"Total stations assessed: {data.get('total_stations', 0)}",
        f"Top {data.get('top_k', 0)} priorities shown.",
        "",
    ]

    for i, station in enumerate(ranked, start=1):
        lines.append(f"{i}. {station.get('station_name', station.get('station_id', 'Unknown'))}")
        lines.append(f"   Priority: {station.get('priority_level', 'N/A')} (score: {station.get('priority_score', 0)})")
        lines.append(f"   PM2.5: {station.get('predicted_pm25', 'N/A')} &#181;g/m\u00B3 ({station.get('risk_category', 'N/A')})")
        lines.append(f"   Engine: {station.get('forecast_engine', 'N/A')} | Confidence: {station.get('confidence_level', 'N/A')}")
        lines.append(f"   Focus: {station.get('recommended_inspection_focus', 'General investigation')}")
        lines.append("")

    lines.append(f"Investigation disclaimer: {disclaimer}")
    lines.append("")
    lines.append("This plan is based on forecast signals and station data quality. It is a prioritization tool, not a determination of violations.")
    return "\n".join(lines)


def render_citizen_advisory(data: dict[str, Any]) -> str:
    station = data.get("station_name", data.get("station_id", "Unknown"))
    headline = data.get("headline", "")
    recommendations = data.get("recommendations", [])
    caution = data.get("caution_note", "")
    conf_level = data.get("confidence_level", "Unavailable")
    lang_served = data.get("language_served", "en")
    fallback = data.get("translation_fallback", False)
    disclaimer = MEDICAL_DISCLAIMER

    lines = [
        f"Advisory for {station}",
        f"Headline: {headline}",
        "",
        "Recommendations:",
    ]

    for rec in recommendations:
        lines.append(f"- {rec}")

    if caution:
        lines.append(f"Caution: {caution}")

    lines.append(f"Confidence: {conf_level}")
    lines.append(f"Language served: {lang_served}")

    if fallback:
        lines.append("Note: Requested language not available. English shown.")

    lines.append(f"Medical disclaimer: {disclaimer}")
    return "\n".join(lines)


def render_city_briefing(data: dict[str, Any]) -> str:
    city = data.get("city", "Bengaluru")
    risk = data.get("city_risk_level", "Unavailable")
    summary = data.get("executive_summary", "")
    recs = data.get("operational_recommendations", [])
    limits = data.get("data_limitations", [])
    stations = data.get("station_summaries", [])

    lines = [
        f"City Briefing: {city}",
        f"City risk level: {risk}",
        f"Summary: {summary}",
        "",
        "Station coverage:",
    ]

    for s in stations:
        lines.append(f"- {s.get('station_name', s.get('station_id', 'N/A'))}: {s.get('predicted_pm25', 'N/A')} &#181;g/m\u00B3 ({s.get('risk_category', 'N/A')}) [{s.get('forecast_engine', 'N/A')}]")

    if recs:
        lines.append("")
        lines.append("Recommendations:")
        for r in recs:
            lines.append(f"- {r}")

    if limits:
        lines.append("")
        lines.append("Data limitations:")
        for l in limits:
            lines.append(f"- {l}")

    lines.append("")
    lines.append("This briefing represents monitored stations only and does not represent unmonitored areas.")
    return "\n".join(lines)
