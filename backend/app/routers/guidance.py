from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.config import KNOWLEDGE_TOP_K_DEFAULT, KNOWLEDGE_TOP_K_MAX
from backend.app.schemas.guidance import (
    GuidanceDocumentInfo,
    GuidanceDocumentListResponse,
    GuidanceSearchResponse,
    GuidanceStatusResponse,
)
from backend.app.services.policy_guidance_service import (
    get_index_status,
    list_eligible_documents,
    search_policy_guidance,
)

router = APIRouter(prefix="/guidance", tags=["guidance"])


@router.get(
    "/search",
    response_model=GuidanceSearchResponse,
    summary="Search for policy or health guidance",
    description="Retrieve relevant passages from the local curated knowledge base "
    "of official policy and health guidance documents.",
)
def guidance_search(
    q: str = Query(..., min_length=1, description="Search query"),
    city: str | None = Query(default=None, description="City filter"),
    source_types: str | None = Query(default=None, description="Comma-separated source types: policy,health_guidance,standard,advisory"),
    top_k: int = Query(default=KNOWLEDGE_TOP_K_DEFAULT, ge=1, le=KNOWLEDGE_TOP_K_MAX, description="Number of results"),
) -> GuidanceSearchResponse:
    st_list = None
    if source_types is not None and isinstance(source_types, str):
        st_list = [s.strip() for s in source_types.split(",") if s.strip()]

    status = get_index_status()
    if not status["index_built"]:
        raise HTTPException(status_code=503, detail="Knowledge base index has not been built. Run: python -m pipeline.build_knowledge_index")

    result = search_policy_guidance(
        query=q,
        city=city,
        source_types=st_list,
        top_k=top_k,
    )
    return GuidanceSearchResponse(**result)


@router.get(
    "/documents",
    response_model=GuidanceDocumentListResponse,
    summary="List citation-eligible documents in the corpus",
    description="Returns metadata for documents that are allowed for citation. "
    "Does not include demo-only documents.",
)
def guidance_documents() -> GuidanceDocumentListResponse:
    docs = list_eligible_documents()
    return GuidanceDocumentListResponse(
        documents=[GuidanceDocumentInfo(**d) for d in docs],
        total_count=len(docs),
    )


@router.get(
    "/status",
    response_model=GuidanceStatusResponse,
    summary="Get knowledge base index status",
    description="Returns whether the index is built, retrieval mode, and document counts.",
)
def guidance_status() -> GuidanceStatusResponse:
    return GuidanceStatusResponse(**get_index_status())
