"""Phase 2 i18n: citizen advisory HI/KN + deterministic summary language notes."""

from __future__ import annotations

from backend.app.agents.grounding import deterministic_summary_from_tools
from backend.app.services.citizen_advisory_service import (
    MEDICAL_DISCLAIMER_BY_LANG,
    _ADVISORY_BY_LANG,
    get_citizen_advisory,
)


class TestAdvisoryCoverage:
    def test_all_risk_bands_in_hi_kn(self):
        for lang in ("hi", "kn"):
            table = _ADVISORY_BY_LANG[lang]
            for band in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"):
                assert band in table, f"{lang} missing {band}"
                assert table[band]["headline"]
                assert table[band]["recommendations"]
                assert table[band]["caution_note"]

    def test_disclaimers_present(self):
        assert "en" in MEDICAL_DISCLAIMER_BY_LANG
        assert "hi" in MEDICAL_DISCLAIMER_BY_LANG
        assert "kn" in MEDICAL_DISCLAIMER_BY_LANG


class TestDeterministicSummaryLanguage:
    def test_hi_note_appended(self):
        text = deterministic_summary_from_tools(
            "enforcement?",
            {
                "get_enforcement_priority": {
                    "ranked_hexagons": [
                        {
                            "location_name": "Peenya",
                            "priority_score": 0.9,
                            "source_attribution": {"traffic": 0.5},
                            "fused_pm25": 55,
                        }
                    ]
                }
            },
            language="hi",
        )
        assert "Peenya" in text or "priority" in text.lower()
        assert "अंग्रेज़ी" in text or "LLM" in text

    def test_advisory_tool_prefers_localized(self):
        text = deterministic_summary_from_tools(
            "guidance",
            {
                "get_citizen_advisory": {
                    "headline": "वायु गुणवत्ता संतोषजनक है।",
                    "recommendations": ["सामान्य बाहरी गतिविधियाँ आमतौर पर उपयुक्त हैं।"],
                    "caution_note": "कोई विशेष सावधानी नहीं।",
                    "medical_disclaimer": MEDICAL_DISCLAIMER_BY_LANG["hi"],
                }
            },
            language="hi",
        )
        assert "वायु" in text
        assert "सामान्य" in text


class TestLiveAdvisoryAllBandsViaService:
    def test_hi_kn_match_risk_category(self):
        for lang in ("hi", "kn", "en"):
            r = get_citizen_advisory("cpcb_hebbal", language=lang)
            assert r["translation_fallback"] is False
            assert r["language_served"] == lang
            assert r["headline"]
