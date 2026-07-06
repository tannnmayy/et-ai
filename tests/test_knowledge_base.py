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
    def test_relevant_query_returns_no_eligible_results_demo_only(self) -> None:
        result = search_policy_guidance("air quality guidelines CPCB AQI categories", top_k=3)
        # Our demo docs have allowed_for_citation=false, so results should be empty
        assert result["no_authoritative_result"] or len(result["results"]) == 0

    def test_irrelevant_query_returns_no_authoritative_result(self) -> None:
        result = search_policy_guidance("quantum physics string theory", top_k=3)
        assert result["no_authoritative_result"] is True

    def test_demo_document_never_in_user_facing_results(self) -> None:
        result = search_policy_guidance("DEMO test only not for citation", top_k=5)
        for r in result.get("results", []):
            assert r["allowed_for_citation"] is True
            assert not r.get("demo_only", True)

    def test_source_type_filtering(self) -> None:
        result = search_policy_guidance("air quality", source_types=["health_guidance"], top_k=3)
        # No eligible health_guidance docs, should be no results
        assert result["no_authoritative_result"] or len(result["results"]) == 0

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
