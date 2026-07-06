from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from backend.app.config import (
    KNOWLEDGE_BASE_DIR,
    KNOWLEDGE_CHUNKS_PATH,
    KNOWLEDGE_INDEX_DIR,
    KNOWLEDGE_MANIFEST_PATH,
    KNOWLEDGE_MIN_RELEVANCE_SCORE,
    KNOWLEDGE_RETRIEVAL_MODE,
    KNOWLEDGE_TOP_K_DEFAULT,
    KNOWLEDGE_TOP_K_MAX,
    get_project_root,
)

logger = logging.getLogger(__name__)

_INDEX_CACHE: dict[str, Any] = {}


def _kb_paths() -> dict[str, Path]:
    root = get_project_root()
    kb = root / KNOWLEDGE_BASE_DIR
    return {
        "root": kb,
        "manifest": kb / KNOWLEDGE_MANIFEST_PATH,
        "chunks": kb / KNOWLEDGE_CHUNKS_PATH,
        "index_dir": kb / KNOWLEDGE_INDEX_DIR,
        "reports": kb / "reports",
    }


def _load_index() -> dict[str, Any]:
    if _INDEX_CACHE:
        return _INDEX_CACHE

    paths = _kb_paths()
    index_meta_path = paths["index_dir"] / "index_metadata.json"
    if not index_meta_path.exists():
        raise FileNotFoundError("Knowledge base index has not been built. Run: python -m pipeline.build_knowledge_index")

    index_meta = json.loads(index_meta_path.read_text(encoding="utf-8"))

    chunks_path = paths["chunks"]
    if not chunks_path.exists():
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

    chunks: list[dict] = []
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    retrieval_mode = index_meta.get("retrieval_mode", KNOWLEDGE_RETRIEVAL_MODE)
    vectorizer = None
    tfidf_matrix = None
    model = None
    embeddings = None

    if retrieval_mode == "lexical":
        import joblib
        vec_path = paths["index_dir"] / "tfidf_vectorizer.joblib"
        mat_path = paths["index_dir"] / "tfidf_matrix.joblib"
        if vec_path.exists() and mat_path.exists():
            vectorizer = joblib.load(str(vec_path))
            tfidf_matrix = joblib.load(str(mat_path))
    elif retrieval_mode == "semantic":
        import joblib
        model_path = paths["index_dir"] / "embedding_model.joblib"
        emb_path = paths["index_dir"] / "embeddings.npy"
        if model_path.exists() and emb_path.exists():
            model = joblib.load(str(model_path))
            embeddings = np.load(str(emb_path))

    cache = {
        "chunks": chunks,
        "retrieval_mode": retrieval_mode,
        "vectorizer": vectorizer,
        "tfidf_matrix": tfidf_matrix,
        "model": model,
        "embeddings": embeddings,
        "index_meta": index_meta,
        "paths": paths,
    }
    _INDEX_CACHE.update(cache)
    return cache


def clear_index_cache() -> None:
    _INDEX_CACHE.clear()


def _retrieve_lexical(
    query: str,
    chunks: list[dict],
    vectorizer,
    tfidf_matrix,
    top_k: int,
) -> list[tuple[int, float]]:
    query_vec = vectorizer.transform([query])
    scores = cosine_similarity(query_vec, tfidf_matrix).flatten()
    top_indices = scores.argsort()[::-1][:top_k]
    return [(int(i), float(scores[i])) for i in top_indices if scores[i] >= KNOWLEDGE_MIN_RELEVANCE_SCORE]


def _retrieve_semantic(
    query: str,
    chunks: list[dict],
    model,
    embeddings: np.ndarray,
    top_k: int,
) -> list[tuple[int, float]]:
    query_vec = model.encode([query])
    scores = cosine_similarity(query_vec, embeddings).flatten()
    top_indices = scores.argsort()[::-1][:top_k]
    return [(int(i), float(scores[i])) for i in top_indices if scores[i] >= KNOWLEDGE_MIN_RELEVANCE_SCORE]


def _build_citation_label(rank: int, doc: dict) -> str:
    org_abbr = doc.get("organization", "Source")[:20]
    year = ""
    if doc.get("publication_date"):
        try:
            year = doc["publication_date"][:4]
        except Exception:
            pass
    return f"[{rank}] {org_abbr}{' (' + year + ')' if year else ''}"


def search_policy_guidance(
    query: str,
    city: str | None = None,
    source_types: list[str] | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    if not query or not query.strip():
        return {
            "query": query,
            "retrieval_mode": "none",
            "results": [],
            "no_authoritative_result": True,
            "warnings": ["Query is empty."],
            "index_status": None,
        }

    query = query.strip()
    top_k = max(1, min(top_k, KNOWLEDGE_TOP_K_MAX))

    try:
        index = _load_index()
    except FileNotFoundError as e:
        return {
            "query": query,
            "retrieval_mode": "none",
            "results": [],
            "no_authoritative_result": True,
            "warnings": [str(e)],
            "index_status": None,
        }

    chunks = index["chunks"]
    retrieval_mode = index["retrieval_mode"]

    if source_types:
        filtered_indices = [
            i for i, c in enumerate(chunks)
            if c.get("source_type") in source_types
        ]
        if not filtered_indices:
            return {
                "query": query,
                "retrieval_mode": retrieval_mode,
                "results": [],
                "no_authoritative_result": True,
                "warnings": [f"No documents found for source types: {source_types}"],
                "index_status": index.get("index_meta"),
            }
        filtered_chunks = [chunks[i] for i in filtered_indices]
    else:
        filtered_indices = list(range(len(chunks)))
        filtered_chunks = chunks

    if retrieval_mode == "semantic" and index.get("model") is not None and index.get("embeddings") is not None:
        if source_types:
            sub_embeddings = index["embeddings"][filtered_indices]
            results = _retrieve_semantic(query, filtered_chunks, index["model"], sub_embeddings, top_k)
            results = [(filtered_indices[i], s) for i, s in results]
        else:
            results = _retrieve_semantic(query, chunks, index["model"], index["embeddings"], top_k)
    elif retrieval_mode == "lexical" and index.get("vectorizer") is not None and index.get("tfidf_matrix") is not None:
        if source_types:
            sub_matrix = index["tfidf_matrix"][filtered_indices]
            results = _retrieve_lexical(query, filtered_chunks, index["vectorizer"], sub_matrix, top_k)
            results = [(filtered_indices[i], s) for i, s in results]
        else:
            results = _retrieve_lexical(query, chunks, index["vectorizer"], index["tfidf_matrix"], top_k)
    else:
        return {
            "query": query,
            "retrieval_mode": retrieval_mode,
            "results": [],
            "no_authoritative_result": True,
            "warnings": [f"Retrieval mode '{retrieval_mode}' index data is missing or incomplete."],
            "index_status": index.get("index_meta"),
        }

    eligible_results = []
    for idx, score in results:
        chunk = chunks[idx]
        if chunk.get("demo_only") or not chunk.get("allowed_for_citation"):
            continue
        eligible_results.append({
            "rank": len(eligible_results) + 1,
            "chunk_id": chunk.get("chunk_id", ""),
            "document_id": chunk.get("document_id", ""),
            "title": chunk.get("title", ""),
            "organization": chunk.get("organization", ""),
            "source_type": chunk.get("source_type", ""),
            "jurisdiction": chunk.get("jurisdiction", ""),
            "publication_date": chunk.get("publication_date"),
            "source_url": chunk.get("source_url"),
            "page_number": chunk.get("page_number"),
            "section_heading": chunk.get("section_heading"),
            "excerpt": chunk.get("text", "")[:500],
            "relevance_score": round(score, 4),
            "citation_label": _build_citation_label(len(eligible_results) + 1, chunk),
            "allowed_for_citation": True,
        })
        if len(eligible_results) >= top_k:
            break

    warnings: list[str] = []
    no_authoritative = False

    if not eligible_results:
        no_authoritative = True
        warnings.append("No sufficiently relevant authoritative source was found in the local curated corpus.")

    return {
        "query": query,
        "retrieval_mode": retrieval_mode,
        "results": eligible_results,
        "no_authoritative_result": no_authoritative,
        "warnings": warnings,
        "index_status": index.get("index_meta"),
    }


def list_eligible_documents() -> list[dict]:
    paths = _kb_paths()
    manifest_path = paths["manifest"]
    if not manifest_path.exists():
        return []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs = manifest.get("documents", [])
    eligible = []
    for doc in docs:
        if not doc.get("demo_only", True) and doc.get("allowed_for_citation", False):
            eligible.append({
                "document_id": doc.get("document_id"),
                "title": doc.get("title"),
                "organization": doc.get("organization"),
                "source_type": doc.get("source_type"),
                "jurisdiction": doc.get("jurisdiction"),
                "publication_date": doc.get("publication_date"),
                "source_url": doc.get("source_url"),
                "demo_only": doc.get("demo_only"),
                "allowed_for_citation": doc.get("allowed_for_citation"),
            })
    return eligible


def get_index_status() -> dict[str, Any]:
    paths = _kb_paths()
    index_meta_path = paths["index_dir"] / "index_metadata.json"

    if not index_meta_path.exists():
        return {
            "index_built": False,
            "retrieval_mode": "none",
            "corpus_document_count": 0,
            "eligible_citation_document_count": 0,
            "chunk_count": 0,
            "last_build_time": None,
            "warnings": ["Index has not been built. Run: python -m pipeline.build_knowledge_index"],
        }

    meta = json.loads(index_meta_path.read_text(encoding="utf-8"))
    return {
        "index_built": True,
        "retrieval_mode": meta.get("retrieval_mode", "unknown"),
        "corpus_document_count": meta.get("total_documents", 0),
        "eligible_citation_document_count": meta.get("eligible_citation_documents", 0),
        "chunk_count": meta.get("total_chunks", 0),
        "last_build_time": meta.get("index_built_at"),
        "warnings": [],
    }


def format_policy_citations(results: list[dict]) -> list[dict]:
    return [
        {
            "citation_label": r.get("citation_label", f"[{r['rank']}]"),
            "title": r.get("title", ""),
            "organization": r.get("organization", ""),
            "source_type": r.get("source_type", ""),
            "jurisdiction": r.get("jurisdiction", ""),
            "source_url": r.get("source_url"),
            "excerpt": r.get("excerpt", "")[:200],
        }
        for r in results
    ]
