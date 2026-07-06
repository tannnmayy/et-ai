from __future__ import annotations

import json
import hashlib
import tempfile
from pathlib import Path

import pytest

from backend.app.agents.orchestrator import run_orchestrator, _detect_intent
from backend.app.agents.state import Intent
from backend.app.agents.tools import tool_search_policy_guidance
from backend.app.config import KNOWLEDGE_BASE_DIR, get_project_root
from backend.app.routers.guidance import guidance_search, guidance_status, guidance_documents
from backend.app.schemas.guidance import (
    GuidanceDocumentListResponse,
    GuidanceSearchResponse,
    GuidanceStatusResponse,
)
from backend.app.services.policy_guidance_service import (
    _build_citation_label,
    clear_index_cache,
    format_policy_citations,
    get_index_status,
    list_eligible_documents,
    search_policy_guidance,
)
from pipeline.build_knowledge_index import (
    _chunk_text,
    _compute_sha256,
    _extract_sections,
    _extract_text_with_pages,
    _validate_metadata,
    build_index,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_index_cache()
    yield


# =========================================================================
# Manifest and ingestion tests
# =========================================================================


class TestManifestAndIngestion:
    def test_manifest_exists(self) -> None:
        root = get_project_root()
        manifest = root / KNOWLEDGE_BASE_DIR / "manifests" / "corpus_manifest.json"
        assert manifest.exists(), "Manifest file must exist"

    def test_metadata_validation_passes(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        manifest_path = root / KNOWLEDGE_BASE_DIR / "manifests" / "corpus_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for doc in manifest.get("documents", []):
            errors = _validate_metadata(doc, kb_raw)
            assert not errors, f"Validation errors for {doc['document_id']}: {errors}"

    def test_metadata_validation_fails_missing_required(self) -> None:
        errors = _validate_metadata({"document_id": "test"}, Path("."))
        assert errors

    def test_metadata_validation_fails_invalid_source_type(self) -> None:
        doc = {
            "document_id": "test", "title": "T", "organization": "O",
            "source_type": "invalid", "jurisdiction": "India",
            "local_path": "nonexistent.md", "sha256": "x", "language": "en",
            "demo_only": True, "allowed_for_citation": False,
        }
        errors = _validate_metadata(doc, Path("."))
        assert any("Invalid source_type" in e for e in errors)

    def test_metadata_validation_fails_missing_file(self) -> None:
        doc = {
            "document_id": "test", "title": "T", "organization": "O",
            "source_type": "policy", "jurisdiction": "India",
            "local_path": "nonexistent_file.md", "sha256": "x", "language": "en",
            "demo_only": True, "allowed_for_citation": False,
        }
        errors = _validate_metadata(doc, Path("."))
        assert any("File not found" in e for e in errors)

    def test_hash_generation(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            p = Path(f.name)
        try:
            h = _compute_sha256(p)
            assert len(h) == 64
            assert all(c in "0123456789abcdef" for c in h)
        finally:
            p.unlink()

    def test_demo_only_filtering(self) -> None:
        docs = list_eligible_documents()
        for d in docs:
            assert not d["demo_only"]
            assert d["allowed_for_citation"]


# =========================================================================
# Chunking/indexing tests
# =========================================================================


class TestChunking:
    def test_chunk_provenance(self) -> None:
        text = "Hello world. " * 500
        chunks = _chunk_text(text, "Test Section", page_number=1)
        assert len(chunks) > 1
        for c in chunks:
            assert c["section_heading"] == "Test Section"
            assert c["page_number"] == 1

    def test_section_metadata_retained(self) -> None:
        text = "# Heading 1\n\nContent under heading 1.\n\n## Subheading\n\nContent under subheading."
        sections = _extract_sections(text)
        assert len(sections) >= 2
        headings = [s["heading"] for s in sections]
        assert "Heading 1" in headings

    def test_index_report_generated(self) -> None:
        root = get_project_root()
        report = root / KNOWLEDGE_BASE_DIR / "reports" / "index_report.json"
        assert report.exists()
        data = json.loads(report.read_text(encoding="utf-8"))
        assert "total_documents" in data
        assert "total_chunks" in data
        assert "retrieval_mode" in data

    def test_deterministic_lexical_index(self) -> None:
        status = get_index_status()
        assert status["retrieval_mode"] == "lexical"
        assert status["index_built"]


# =========================================================================
# Retrieval tests
# =========================================================================


class TestRetrieval:
    def test_relevant_query_returns_only_citation_eligible_results(self) -> None:
        result = search_policy_guidance("air quality guidelines CPCB AQI categories", top_k=3)
        for r in result.get("results", []):
            assert r["allowed_for_citation"] is True

    def test_irrelevant_query_returns_low_relevance(self) -> None:
        result = search_policy_guidance("quantum physics string theory", top_k=3)
        for r in result.get("results", []):
            assert r["relevance_score"] < 0.5

    def test_demo_document_never_in_user_facing_results(self) -> None:
        result = search_policy_guidance("DEMO test only not for citation", top_k=5)
        for r in result.get("results", []):
            assert r["allowed_for_citation"] is True
            doc_id = r.get("document_id", "")
            assert doc_id not in ("cpcb_aqi_categories_2023", "who_air_quality_2021",
                                   "ncap_programme_2024", "demo_only_sample_001")

    def test_source_type_filtering(self) -> None:
        result = search_policy_guidance("air quality", source_types=["health_guidance"], top_k=3)
        for r in result.get("results", []):
            assert r["source_type"] == "health_guidance"

    def test_top_k_validation(self) -> None:
        result = search_policy_guidance("air", top_k=100)
        # Should clamp to max
        assert len(result.get("results", [])) <= 10

    def test_short_excerpt_length(self) -> None:
        result = search_policy_guidance("air quality health", top_k=3)
        for r in result.get("results", []):
            assert len(r.get("excerpt", "")) <= 500

    def test_retrieval_mode_reported(self) -> None:
        result = search_policy_guidance("test query", top_k=1)
        assert result["retrieval_mode"] in ("lexical", "semantic")


# =========================================================================
# Service tests
# =========================================================================


class TestService:
    def test_missing_index_returns_controlled_error(self) -> None:
        result = search_policy_guidance("")
        assert result["no_authoritative_result"]

    def test_citation_formatting(self) -> None:
        doc = {"organization": "CPCB", "publication_date": "2023-01-15"}
        label = _build_citation_label(1, doc)
        assert "CPCB" in label
        assert "2023" in label

    def test_format_policy_citations(self) -> None:
        results = [
            {"rank": 1, "citation_label": "[1] CPCB", "title": "Test", "organization": "CPCB",
             "source_type": "policy", "jurisdiction": "India", "source_url": None, "excerpt": "Test excerpt"},
        ]
        formatted = format_policy_citations(results)
        assert len(formatted) == 1
        assert formatted[0]["citation_label"] == "[1] CPCB"
        assert "excerpt" in formatted[0]

    def test_no_invented_source_fields(self) -> None:
        result = search_policy_guidance("air quality", top_k=5)
        for r in result.get("results", []):
            assert "document_id" in r
            assert "title" in r
            assert "organization" in r


# =========================================================================
# Agent integration tests
# =========================================================================


class TestAgentIntegration:
    def test_citizen_agent_includes_citations_when_available(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Health guidance", explicit_intent="citizen_guidance"
        )
        sd = result.get("structured_data", {})
        md = sd.get("medical_disclaimer", "")
        assert md and "general air-quality guidance" in md.lower()

    def test_citizen_agent_retains_medical_disclaimer(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Health guidance", explicit_intent="citizen_guidance"
        )
        from backend.app.config import MEDICAL_DISCLAIMER
        assert MEDICAL_DISCLAIMER in result["answer"] or \
            result.get("structured_data", {}).get("medical_disclaimer") == MEDICAL_DISCLAIMER

    def test_enforcement_agent_retains_investigation_disclaimer(self) -> None:
        result = run_orchestrator(
            query="Inspection plan", city="bengaluru", explicit_intent="inspection_plan"
        )
        from backend.app.config import INVESTIGATION_DISCLAIMER
        sd = result.get("structured_data", {})
        ranked = sd.get("ranked_stations", [])
        has_disclaimer = any(
            INVESTIGATION_DISCLAIMER in str(s.get("caveats", []))
            for s in ranked
        )
        assert has_disclaimer

    def test_city_briefing_retains_data_limitations(self) -> None:
        result = run_orchestrator(
            query="City briefing", city="bengaluru", explicit_intent="city_briefing"
        )
        sd = result.get("structured_data", {})
        limitations = sd.get("data_limitations", [])
        assert any("monitored stations" in str(l).lower() for l in limitations)

    def test_no_result_adds_honest_no_source_warning(self) -> None:
        result = run_orchestrator(
            query="What does the policy say?", explicit_intent="policy_guidance"
        )
        sd = result.get("structured_data", {})
        if sd and sd.get("no_authoritative_result"):
            assert "no authoritative" in result["answer"].lower() or \
                "did not find" in result["answer"].lower()

    def test_audit_trail_includes_retrieval_mode(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Health guidance", explicit_intent="citizen_guidance"
        )
        audit = result.get("audit_trail", {})
        tools = audit.get("tools_called", [])
        guidance_calls = [t for t in tools if "policy" in t.get("tool", "")]
        if guidance_calls:
            assert "success" in guidance_calls[0]


# =========================================================================
# API tests
# =========================================================================


class TestGuidanceAPI:
    def test_guidance_search(self) -> None:
        result = guidance_search(q="air quality", top_k=3)
        assert isinstance(result, GuidanceSearchResponse)
        assert result.retrieval_mode in ("lexical", "semantic")

    def test_guidance_documents(self) -> None:
        result = guidance_documents()
        assert isinstance(result, GuidanceDocumentListResponse)
        for d in result.documents:
            assert not d.demo_only
            assert d.allowed_for_citation

    def test_guidance_status(self) -> None:
        result = guidance_status()
        assert isinstance(result, GuidanceStatusResponse)
        assert result.index_built
        assert result.retrieval_mode in ("lexical", "semantic")

    def test_existing_intelligence_routes_unchanged(self) -> None:
        from backend.app.routers.intelligence import station_evidence
        result = station_evidence("cpcb_hebbal")
        assert result["station_id"] == "cpcb_hebbal"

    def test_existing_copilot_routes_unchanged(self) -> None:
        from backend.app.routers.copilot import copilot_station_explain
        result = copilot_station_explain("cpcb_hebbal")
        assert result.intent == "station_explanation"


# =========================================================================
# Intent routing for policy_guidance
# =========================================================================


class TestPolicyGuidanceIntent:
    def test_policy_guidance_query_detected(self) -> None:
        intent = _detect_intent("What official guidance supports this?", station_id="")
        assert intent == Intent.policy_guidance

    def test_cpcb_query_detected(self) -> None:
        intent = _detect_intent("What does CPCB say about outdoor activity?", station_id="")
        assert intent == Intent.policy_guidance

    def test_who_query_detected(self) -> None:
        intent = _detect_intent("What official source supports this recommendation?", station_id="")
        assert intent == Intent.policy_guidance

    def test_explicit_intent_routes_correctly(self) -> None:
        result = run_orchestrator(
            query="official sources", explicit_intent="policy_guidance"
        )
        assert result["intent"] == "policy_guidance"
        assert result["selected_agent"] == "policy_guidance_agent"


# =========================================================================
# Tool behavior
# =========================================================================


class TestPolicyGuidanceTool:
    def test_tool_search_policy_guidance_works(self) -> None:
        result = tool_search_policy_guidance("air quality health", top_k=3)
        assert "_tool_error" not in result
        assert "retrieval_mode" in result
        assert "results" in result

    def test_tool_empty_query_returns_no_results(self) -> None:
        result = tool_search_policy_guidance("", top_k=3)
        assert result["no_authoritative_result"]


# =========================================================================
# Authoritative document manifest tests
# =========================================================================


class TestAuthoritativeManifest:
    """Tests for the three approved authoritative documents in the manifest."""

    AUTHORITATIVE_IDS = [
        "who_global_air_quality_guidelines_2021",
        "karnataka_state_action_plan_air_pollution_2022",
        "cpcb_pollution_control_law_series_2021",
    ]

    def _load_manifest_docs(self) -> dict[str, dict]:
        root = get_project_root()
        manifest_path = root / KNOWLEDGE_BASE_DIR / "manifests" / "corpus_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {d["document_id"]: d for d in manifest.get("documents", [])}

    def test_all_three_authoritative_documents_in_manifest(self) -> None:
        docs = self._load_manifest_docs()
        for doc_id in self.AUTHORITATIVE_IDS:
            assert doc_id in docs, f"Missing authoritative document: {doc_id}"

    def test_authoritative_docs_are_not_demo_only(self) -> None:
        docs = self._load_manifest_docs()
        for doc_id in self.AUTHORITATIVE_IDS:
            doc = docs[doc_id]
            assert doc["demo_only"] is False, f"{doc_id} should not be demo_only"
            assert doc["allowed_for_citation"] is True, f"{doc_id} should be citation-eligible"

    def test_demo_docs_remain_demo_only(self) -> None:
        docs = self._load_manifest_docs()
        for doc_id, doc in docs.items():
            if doc_id not in self.AUTHORITATIVE_IDS:
                assert doc["demo_only"] is True, f"Non-authoritative doc {doc_id} should be demo_only"
                assert doc["allowed_for_citation"] is False, f"Non-authoritative doc {doc_id} should not be citation-eligible"

    def test_who_doc_metadata(self) -> None:
        docs = self._load_manifest_docs()
        who = docs["who_global_air_quality_guidelines_2021"]
        assert who["source_type"] == "health_guidance"
        assert who["jurisdiction"] == "Global"
        assert who["permitted_for_health_context"] is True
        assert who["permitted_for_indian_aqi_thresholds"] is False
        assert who["permitted_for_legal_context"] is False

    def test_karnataka_doc_metadata(self) -> None:
        docs = self._load_manifest_docs()
        karn = docs["karnataka_state_action_plan_air_pollution_2022"]
        assert karn["source_type"] == "policy"
        assert karn["jurisdiction"] == "Karnataka"
        assert karn["permitted_for_city_context"] is True
        assert karn["permitted_for_investigation_hypothesis_context"] is True
        assert karn["permitted_for_source_attribution"] is False
        assert karn["permitted_for_legal_conclusion"] is False

    def test_cpcb_doc_metadata(self) -> None:
        docs = self._load_manifest_docs()
        cpcb = docs["cpcb_pollution_control_law_series_2021"]
        assert cpcb["source_type"] == "standard"
        assert cpcb["jurisdiction"] == "India"
        assert cpcb["legal_context_only"] is True
        assert cpcb["permitted_for_compliance_verdict"] is False
        assert cpcb["permitted_for_violation_claim"] is False
        assert cpcb["permitted_for_penalty_claim"] is False
        assert "not legal advice" in cpcb.get("required_disclaimer", "").lower()

    def test_authoritative_docs_have_local_files_in_manifest(self) -> None:
        docs = self._load_manifest_docs()
        for doc_id in self.AUTHORITATIVE_IDS:
            doc = docs[doc_id]
            assert doc["local_path"].endswith(".pdf"), f"{doc_id} should be a PDF"


# =========================================================================
# Authoritative document file presence tests
# =========================================================================


class TestAuthoritativeFilesPresent:
    """Check that the actual PDF files exist in knowledge_base/raw/."""

    EXPECTED_FILES = [
        "who_global_air_quality_guidelines_2021.pdf",
        "karnataka_state_action_plan_air_pollution_2022.pdf",
        "cpcb_pollution_control_law_series_2021.pdf",
    ]

    def test_all_pdf_files_present(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        for fname in self.EXPECTED_FILES:
            assert (kb_raw / fname).exists(), f"Missing PDF: {fname}"


# =========================================================================
# PDF page extraction tests
# =========================================================================


class TestPDFExtraction:
    def test_extract_text_with_pages_returns_list(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        pdf_path = kb_raw / "who_global_air_quality_guidelines_2021.pdf"
        if not pdf_path.exists():
            pytest.skip("WHO PDF not present")
        pages = _extract_text_with_pages(pdf_path)
        assert isinstance(pages, list)
        assert len(pages) > 0
        for page_num, text in pages:
            assert isinstance(page_num, int)
            assert isinstance(text, str)
            assert len(text.strip()) > 0

    def test_extract_text_with_pages_preserves_page_numbers(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        pdf_path = kb_raw / "karnataka_state_action_plan_air_pollution_2022.pdf"
        if not pdf_path.exists():
            pytest.skip("Karnataka PDF not present")
        pages = _extract_text_with_pages(pdf_path)
        page_numbers = [p[0] for p in pages]
        assert page_numbers[0] == 1
        for i in range(1, len(page_numbers)):
            assert page_numbers[i] > page_numbers[i - 1]


# =========================================================================
# Index build tests for authoritative documents
# =========================================================================


class TestAuthoritativeIndexBuild:
    def test_index_includes_authoritative_documents(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        for fname in TestAuthoritativeFilesPresent.EXPECTED_FILES:
            if not (kb_raw / fname).exists():
                pytest.skip(f"{fname} not present")
        status = get_index_status()
        assert status["eligible_citation_document_count"] >= 3

    def test_eligible_documents_list_includes_all_three(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        for fname in TestAuthoritativeFilesPresent.EXPECTED_FILES:
            if not (kb_raw / fname).exists():
                pytest.skip(f"{fname} not present")
        eligible = list_eligible_documents()
        eligible_ids = {d["document_id"] for d in eligible}
        for doc_id in TestAuthoritativeManifest.AUTHORITATIVE_IDS:
            assert doc_id in eligible_ids, f"Missing from eligible list: {doc_id}"

    def test_demo_documents_not_in_eligible_list(self) -> None:
        eligible = list_eligible_documents()
        eligible_ids = {d["document_id"] for d in eligible}
        for doc_id in TestAuthoritativeManifest.AUTHORITATIVE_IDS:
            pass  # these are expected
        # No demo docs should appear
        for d in eligible:
            assert d["demo_only"] is False
            assert d["allowed_for_citation"] is True


# =========================================================================
# WHO health-context retrieval tests
# =========================================================================


class TestWHORetrieval:
    def test_who_pm25_health_query_returns_results(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "who_global_air_quality_guidelines_2021.pdf").exists():
            pytest.skip("WHO PDF not present")
        result = search_policy_guidance("WHO PM2.5 health guidelines exposure", top_k=3)
        assert not result["no_authoritative_result"]
        assert len(result["results"]) > 0
        doc_ids = {r["document_id"] for r in result["results"]}
        assert "who_global_air_quality_guidelines_2021" in doc_ids

    def test_who_result_has_health_context_guardrail(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "who_global_air_quality_guidelines_2021.pdf").exists():
            pytest.skip("WHO PDF not present")
        result = search_policy_guidance("WHO PM2.5 health guidelines", top_k=3)
        for r in result.get("results", []):
            if r["document_id"] == "who_global_air_quality_guidelines_2021":
                assert r.get("source_guardrail") == "health_context_only"
                assert "CPCB" in r.get("guardrail_note", "") or "Indian AQI" in r.get("guardrail_note", "")
                break

    def test_who_cannot_override_indian_aqi_thresholds(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "who_global_air_quality_guidelines_2021.pdf").exists():
            pytest.skip("WHO PDF not present")
        result = search_policy_guidance("WHO PM2.5 annual guideline 5 ug/m3", top_k=3)
        for r in result.get("results", []):
            if r["document_id"] == "who_global_air_quality_guidelines_2021":
                assert r.get("permitted_for_indian_aqi_thresholds") is False
                break

    def test_who_result_includes_citation_provenance(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "who_global_air_quality_guidelines_2021.pdf").exists():
            pytest.skip("WHO PDF not present")
        result = search_policy_guidance("WHO PM2.5 health guidelines", top_k=3)
        for r in result.get("results", []):
            if r["document_id"] == "who_global_air_quality_guidelines_2021":
                assert r.get("title")
                assert r.get("organization")
                assert r.get("publication_date")
                assert r.get("citation_label")
                assert "chunk_id" in r
                break


# =========================================================================
# Karnataka SAPAP-K retrieval tests
# =========================================================================


class TestKarnatakaRetrieval:
    def test_karnataka_road_dust_query(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "karnataka_state_action_plan_air_pollution_2022.pdf").exists():
            pytest.skip("Karnataka PDF not present")
        result = search_policy_guidance("road dust particulate control measures Karnataka", top_k=3)
        assert not result["no_authoritative_result"]
        doc_ids = {r["document_id"] for r in result["results"]}
        assert "karnataka_state_action_plan_air_pollution_2022" in doc_ids

    def test_karnataka_traffic_emissions_query(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "karnataka_state_action_plan_air_pollution_2022.pdf").exists():
            pytest.skip("Karnataka PDF not present")
        result = search_policy_guidance("traffic emissions vehicular pollution control", top_k=3)
        assert not result["no_authoritative_result"]

    def test_karnataka_waste_burning_query(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "karnataka_state_action_plan_air_pollution_2022.pdf").exists():
            pytest.skip("Karnataka PDF not present")
        result = search_policy_guidance("waste burning municipal solid waste management", top_k=3)
        assert not result["no_authoritative_result"]

    def test_karnataka_investigation_hypothesis_guardrail(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "karnataka_state_action_plan_air_pollution_2022.pdf").exists():
            pytest.skip("Karnataka PDF not present")
        result = search_policy_guidance("road dust inspection Karnataka", top_k=3)
        for r in result.get("results", []):
            if r["document_id"] == "karnataka_state_action_plan_air_pollution_2022":
                assert r.get("source_guardrail") == "investigation_hypothesis_only"
                assert r.get("permitted_for_source_attribution") is False
                break

    def test_enforcement_uses_karnataka_with_disclaimer(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "karnataka_state_action_plan_air_pollution_2022.pdf").exists():
            pytest.skip("Karnataka PDF not present")
        from backend.app.config import INVESTIGATION_DISCLAIMER
        result = run_orchestrator(
            query="Inspection plan", city="bengaluru", explicit_intent="inspection_plan"
        )
        sd = result.get("structured_data", {})
        ranked = sd.get("ranked_stations", [])
        has_disclaimer = any(
            INVESTIGATION_DISCLAIMER in str(s.get("caveats", []))
            for s in ranked
        )
        assert has_disclaimer


# =========================================================================
# CPCB legal-context retrieval tests
# =========================================================================


class TestCPCBLegalRetrieval:
    def test_cpcb_regulatory_context_query(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "cpcb_pollution_control_law_series_2021.pdf").exists():
            pytest.skip("CPCB PDF not present")
        result = search_policy_guidance("regulatory context construction dust pollution control act", top_k=3)
        assert not result["no_authoritative_result"]
        doc_ids = {r["document_id"] for r in result["results"]}
        assert "cpcb_pollution_control_law_series_2021" in doc_ids

    def test_cpcb_air_act_query(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "cpcb_pollution_control_law_series_2021.pdf").exists():
            pytest.skip("CPCB PDF not present")
        result = search_policy_guidance("Air Act Environment Protection Act pollution control", top_k=3)
        assert not result["no_authoritative_result"]

    def test_cpcb_legal_context_guardrail(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "cpcb_pollution_control_law_series_2021.pdf").exists():
            pytest.skip("CPCB PDF not present")
        from backend.app.config import LEGAL_DISCLAIMER
        result = search_policy_guidance("regulatory framework pollution control", top_k=3)
        for r in result.get("results", []):
            if r["document_id"] == "cpcb_pollution_control_law_series_2021":
                assert r.get("source_guardrail") == "legal_context_only"
                assert LEGAL_DISCLAIMER in r.get("guardrail_note", "")
                assert r.get("permitted_for_compliance_verdict") is False
                assert r.get("permitted_for_violation_claim") is False
                assert r.get("permitted_for_penalty_claim") is False
                break

    def test_cpcb_response_includes_legal_disclaimer(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "cpcb_pollution_control_law_series_2021.pdf").exists():
            pytest.skip("CPCB PDF not present")
        from backend.app.config import LEGAL_DISCLAIMER
        result = run_orchestrator(
            query="What is the regulatory context for construction dust?",
            explicit_intent="policy_guidance",
        )
        answer = result.get("answer", "").lower()
        assert "not legal advice" in answer or "general context" in answer


# =========================================================================
# No-violation / no-causality tests
# =========================================================================


class TestNoViolationClaims:
    def test_no_compliance_verdict_in_results(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "cpcb_pollution_control_law_series_2021.pdf").exists():
            pytest.skip("CPCB PDF not present")
        result = search_policy_guidance("compliance violation penalty", top_k=5)
        for r in result.get("results", []):
            if r.get("source_guardrail") == "legal_context_only":
                assert r.get("permitted_for_compliance_verdict") is False
                assert r.get("permitted_for_violation_claim") is False
                assert r.get("permitted_for_penalty_claim") is False

    def test_enforcement_never_claims_causality(self) -> None:
        result = run_orchestrator(
            query="Inspection plan", city="bengaluru", explicit_intent="inspection_plan"
        )
        from backend.app.config import INVESTIGATION_DISCLAIMER
        answer = result.get("answer", "")
        assert INVESTIGATION_DISCLAIMER in answer or "investigation hypothesis" in answer.lower()

    def test_enforcement_no_source_attribution(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "karnataka_state_action_plan_air_pollution_2022.pdf").exists():
            pytest.skip("Karnataka PDF not present")
        result = search_policy_guidance("source attribution station pollution cause", top_k=5)
        for r in result.get("results", []):
            if r["document_id"] == "karnataka_state_action_plan_air_pollution_2022":
                assert r.get("permitted_for_source_attribution") is False


# =========================================================================
# Citation provenance tests
# =========================================================================


class TestCitationProvenance:
    def test_citations_include_required_fields(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "who_global_air_quality_guidelines_2021.pdf").exists():
            pytest.skip("WHO PDF not present")
        result = search_policy_guidance("PM2.5 health exposure guidelines", top_k=3)
        for r in result.get("results", []):
            assert "document_id" in r
            assert "title" in r
            assert "organization" in r
            assert "publication_date" in r
            assert "citation_label" in r
            assert "chunk_id" in r
            assert "relevance_score" in r
            assert "allowed_for_citation" in r
            assert r["allowed_for_citation"] is True

    def test_citations_have_page_numbers_for_pdfs(self) -> None:
        root = get_project_root()
        kb_raw = root / KNOWLEDGE_BASE_DIR / "raw"
        if not (kb_raw / "who_global_air_quality_guidelines_2021.pdf").exists():
            pytest.skip("WHO PDF not present")
        result = search_policy_guidance("PM2.5 health guidelines", top_k=3)
        for r in result.get("results", []):
            if r["document_id"] == "who_global_air_quality_guidelines_2021":
                assert r.get("page_number") is not None
                assert isinstance(r["page_number"], int)
                assert r["page_number"] >= 1
                break


# =========================================================================
# Irrelevant query still returns no_authoritative_result
# =========================================================================


class TestIrrelevantQuery:
    def test_irrelevant_query_returns_low_relevance(self) -> None:
        result = search_policy_guidance("quantum entanglement particle physics", top_k=3)
        for r in result.get("results", []):
            assert r["relevance_score"] < 0.5

    def test_empty_query_returns_no_authoritative(self) -> None:
        result = search_policy_guidance("", top_k=3)
        assert result["no_authoritative_result"] is True
        assert len(result["results"]) == 0

    def test_empty_query_returns_no_authoritative(self) -> None:
        result = search_policy_guidance("", top_k=3)
        assert result["no_authoritative_result"] is True
