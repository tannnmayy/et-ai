from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GuidanceSearchResult(BaseModel):
    rank: int = Field(ge=1)
    chunk_id: str
    document_id: str
    title: str
    organization: str
    source_type: str
    jurisdiction: str
    publication_date: str | None = None
    source_url: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    excerpt: str
    relevance_score: float = Field(ge=0, le=1)
    citation_label: str
    allowed_for_citation: bool


class GuidanceSearchResponse(BaseModel):
    query: str
    retrieval_mode: str
    results: list[GuidanceSearchResult]
    no_authoritative_result: bool = False
    warnings: list[str] = Field(default_factory=list)
    index_status: dict[str, Any] | None = None


class GuidanceDocumentInfo(BaseModel):
    document_id: str
    title: str
    organization: str
    source_type: str
    jurisdiction: str
    publication_date: str | None = None
    source_url: str | None = None
    demo_only: bool
    allowed_for_citation: bool


class GuidanceDocumentListResponse(BaseModel):
    documents: list[GuidanceDocumentInfo]
    total_count: int


class GuidanceStatusResponse(BaseModel):
    index_built: bool
    retrieval_mode: str
    corpus_document_count: int
    eligible_citation_document_count: int
    chunk_count: int
    last_build_time: str | None = None
    warnings: list[str] = Field(default_factory=list)


class GuidanceCitation(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    organization: str
    source_type: str
    jurisdiction: str
    publication_date: str | None = None
    source_url: str | None = None
    excerpt: str
    relevance_score: float
    citation_label: str
