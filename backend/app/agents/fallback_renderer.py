from __future__ import annotations

from typing import Any

from backend.app.config import (
    INVESTIGATION_DISCLAIMER,
    MEDICAL_DISCLAIMER,
    SCOPE_AQI_COVERAGE,
    SCOPE_NO_TRAFFIC,
    SCOPE_WEATHER_CHANGE,
)


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
        f"Forecast PM2.5: {pm25} µg/m³ ({risk})",
        f"Forecast engine: {engine}",
        f"Explanation method: {method}",
    ]

    if change_val is not None:
        sign = "+" if change_val > 0 else ""
        lines.append(f"Expected change: {sign}{change_val:.1f} µg/m³ ({change_dir})")

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
        lines.append(f"   PM2.5: {station.get('predicted_pm25', 'N/A')} µg/m³ ({station.get('risk_category', 'N/A')})")
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
    disclaimer = data.get("medical_disclaimer") or MEDICAL_DISCLAIMER

    # Shell labels stay short English for copilot render path; body content is localized
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
        if lang_served == "en" and data.get("language_requested") in ("hi", "kn"):
            lines.append("Note: Requested language not fully available. English shown.")
        else:
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
        lines.append(f"- {s.get('station_name', s.get('station_id', 'N/A'))}: {s.get('predicted_pm25', 'N/A')} µg/m³ ({s.get('risk_category', 'N/A')}) [{s.get('forecast_engine', 'N/A')}]")

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


def render_weather_forecast(data: dict[str, Any]) -> str:
    city = data.get("city", "Bengaluru").title()
    provider = data.get("provider", "unknown")
    status = data.get("source_status", "unknown")
    freshness = data.get("freshness", "unknown")
    hourly = data.get("hourly", [])

    lines = [
        f"Weather Forecast for {city}",
        f"Source: {provider} ({status}, {freshness})",
    ]

    if hourly:
        first = hourly[0]
        last = hourly[-1]
        lines.append(f"Period: {first.get('timestamp_local', '')} to {last.get('timestamp_local', '')}")
        lines.append(f"Hours: {len(hourly)}")

    lines.append("")
    lines.append("Hourly data available. Use /weather/summary for aggregated information.")

    if data.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for w in data["warnings"]:
            lines.append(f"- {w}")

    return "\n".join(lines)


def render_weather_summary(data: dict[str, Any]) -> str:
    city = data.get("city", "Bengaluru").title()
    period = data.get("period", "next_24h")
    risk = data.get("weather_risk_level", "Low")
    severe = data.get("severe_weather_present", False)

    lines = [
        f"Weather Summary for {city} ({period.replace('_', ' ')})",
        f"Weather risk level: {risk}",
    ]

    t_min = data.get("temperature_min_c")
    t_max = data.get("temperature_max_c")
    if t_min is not None and t_max is not None:
        lines.append(f"Temperature: {t_min:.0f}–{t_max:.0f} °C")
    elif t_max is not None:
        lines.append(f"Temperature: up to {t_max:.0f} °C")

    at_min = data.get("apparent_temperature_min_c")
    at_max = data.get("apparent_temperature_max_c")
    if at_min is not None and at_max is not None:
        lines.append(f"Feels like: {at_min:.0f}–{at_max:.0f} °C")

    precip = data.get("total_precipitation_mm", 0)
    if precip > 0:
        lines.append(f"Total precipitation: {precip:.1f} mm")
    prob = data.get("max_precipitation_probability_percent")
    if prob is not None:
        lines.append(f"Max rain probability: {prob:.0f}%")

    wind = data.get("max_wind_speed_kmh")
    if wind is not None and wind > 0:
        lines.append(f"Max wind speed: {wind:.0f} km/h")
    gust = data.get("max_wind_gust_kmh")
    if gust is not None and gust > 0:
        lines.append(f"Max wind gust: {gust:.0f} km/h")

    desc = data.get("dominant_weather_description", "")
    if desc and desc != "Unknown":
        lines.append(f"Conditions: {desc}")

    if severe:
        lines.append("Severe weather present.")

    reasons = data.get("weather_risk_reasons", [])
    if reasons:
        lines.append("")
        lines.append("Caution reasons:")
        for r in reasons:
            lines.append(f"- {r}")

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"- {w}")

    lines.append("")
    lines.append(SCOPE_WEATHER_CHANGE)
    return "\n".join(lines)


def render_travel_readiness(data: dict[str, Any]) -> str:
    city = data.get("city", "bengaluru").title()
    profile = data.get("profile", "general")
    period = data.get("period", "next_24h")
    readiness = data.get("final_readiness", "Unavailable")
    basis = data.get("readiness_basis", "unavailable")

    lines = [
        f"Travel Readiness for {city}",
        f"Profile: {profile}",
        f"Period: {period.replace('_', ' ')}",
        f"Readiness: {readiness}",
        f"Assessment basis: {basis.replace('_', ' ')}",
    ]

    weather = data.get("weather_component", {})
    if weather.get("weather_available"):
        w_risk = weather.get("weather_risk_level", "Low")
        lines.append(f"Weather risk: {w_risk}")
        w_summary = weather.get("weather_summary")
        if w_summary:
            lines.append(f"Weather: {w_summary}")
    else:
        lines.append("Weather data: unavailable")

    aqi = data.get("air_quality_component", {})
    if aqi.get("aqi_available"):
        aqi_risk = aqi.get("city_risk_level", "Unavailable")
        lines.append(f"Air quality risk: {aqi_risk}")
    else:
        lines.append("Air quality data: unavailable")

    reasons = data.get("decision_reasons", [])
    if reasons:
        lines.append("")
        lines.append("Decision factors:")
        for r in reasons:
            lines.append(f"- {r}")

    precautions = data.get("profile_specific_precautions", [])
    if precautions:
        lines.append("")
        lines.append("Precautions:")
        for p in precautions:
            lines.append(f"- {p}")

    limitations = data.get("limitations", [])
    if limitations:
        lines.append("")
        lines.append("Limitations:")
        for l in limitations:
            lines.append(f"- {l}")

    disclaimer = data.get("medical_disclaimer")
    if disclaimer:
        lines.append("")
        lines.append(disclaimer)

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"- {w}")

    return "\n".join(lines)


def render_spatial_intelligence(data: dict[str, Any]) -> str:
    station = data.get("station_id", "Unknown")
    lines = [
        f"Spatial Intelligence for Station: {station}",
        "",
    ]
    fe = data.get("forecast_evidence", {})
    if fe:
        lines.append(f"Forecast PM2.5: {fe.get('predicted_pm25', 'N/A')} µg/m³ ({fe.get('risk_category', 'N/A')})")
        lines.append(f"Forecast engine: {fe.get('forecast_engine', 'N/A')}")
        lines.append("")
    fc = data.get("forecast_confidence", {})
    if fc:
        lines.append(f"Confidence: {fc.get('confidence_level', 'N/A')} ({fc.get('confidence_score', 'N/A')}/100)")
        lines.append("")
    ip = data.get("inspection_priority", {})
    if ip:
        lines.append(f"Inspection priority: {ip.get('priority_level', 'N/A')} (score: {ip.get('priority_score', 'N/A')})")
        lines.append(f"Focus: {ip.get('recommended_inspection_focus', 'N/A')}")
        lines.append("")
    geo = data.get("geospatial_context", {})
    if geo:
        lines.append("Geospatial context:")
        lines.append(f"  Build status: {geo.get('build_status', 'unknown')}")
        rc = geo.get("road_context", {}) or {}
        rd = rc.get("road_density_m_per_sq_km")
        if rd is not None:
            lines.append(f"  Road density: {rd:.1f} m/km2")
        lc = geo.get("landuse_context", {}) or {}
        gs = lc.get("green_space_fraction")
        if gs is not None:
            lines.append(f"  Green space fraction: {gs:.2%}")
        lines.append("")
    limitations = data.get("limitations", [])
    if limitations:
        lines.append("Limitations:")
        for lim in limitations:
            lines.append(f"- {lim}")
    return "\n".join(lines)


def render_neighbourhood_comparison(data: dict[str, Any]) -> str:
    from backend.app.config import NEIGHBOURHOOD_SUITABILITY_DISCLAIMER
    candidates = data.get("candidates", [])
    ranking = data.get("ranking")
    lines = [
        "Neighbourhood Suitability Comparison",
        "",
    ]
    if not candidates:
        lines.append("No candidate areas to compare.")
        return "\n".join(lines)
    if ranking:
        lines.append(f"Ranking (best first):")
        for rank_pos, cand_idx in enumerate(ranking, start=1):
            cand = candidates[cand_idx] if cand_idx < len(candidates) else {}
            label = cand.get("candidate_label", f"Candidate {cand_idx + 1}")
            score = cand.get("overall_score")
            score_str = f"{score:.2f}" if score is not None else "N/A"
            lines.append(f"  {rank_pos}. {label} (score: {score_str})")
        lines.append("")
    for i, cand in enumerate(candidates):
        lines.append(f"Candidate {i + 1}: {cand.get('candidate_label', 'Unknown')}")
        score = cand.get("overall_score")
        if score is not None:
            lines.append(f"  Overall score: {score:.2f}")
        else:
            lines.append(f"  Overall score: N/A (insufficient data)")
        lines.append(f"  Partial assessment: {cand.get('partial_assessment', False)}")
        lines.append("")
    lines.append(f"Disclaimer: {NEIGHBOURHOOD_SUITABILITY_DISCLAIMER}")
    return "\n".join(lines)
