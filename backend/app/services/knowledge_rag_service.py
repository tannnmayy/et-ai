"""Legacy sklearn TF-IDF/SVD RAG store (fallback for dense FAISS RAG).

Prefer ``backend.app.services.rag_service.retrieve_relevant_context`` for new
call sites. This module remains as a reliable fallback when sentence-transformers
or FAISS are unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.config import (
    KNOWLEDGE_BASE_DIR,
    KNOWLEDGE_CHUNKS_PATH,
    get_project_root,
)

logger = logging.getLogger(__name__)

STORE_DIR_REL = "knowledge_base/vector_store"
EMBED_DIM = 256

_STORE: dict[str, Any] | None = None
_BUILD_ATTEMPTED = False


def _store_path() -> Path:
    return get_project_root() / STORE_DIR_REL


def _chunks_path() -> Path:
    return get_project_root() / KNOWLEDGE_BASE_DIR / KNOWLEDGE_CHUNKS_PATH


def _load_corpus_documents() -> list[dict[str, Any]]:
    """Load documents for indexing: processed chunks + raw markdown."""
    docs: list[dict[str, Any]] = []
    chunks_file = _chunks_path()
    if chunks_file.exists():
        with chunks_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = (row.get("text") or "").strip()
                if len(text) < 40:
                    continue
                docs.append({
                    "id": row.get("chunk_id") or hashlib.md5(text.encode()).hexdigest()[:16],
                    "text": text,
                    "title": row.get("title") or row.get("document_id") or "Unknown",
                    "source_type": str(row.get("source_type") or "policy"),
                    "organization": str(row.get("organization") or ""),
                    "demo_only": bool(row.get("demo_only", False)),
                    "allowed_for_citation": bool(row.get("allowed_for_citation", True)),
                })

    raw_dir = get_project_root() / KNOWLEDGE_BASE_DIR / "raw"
    if raw_dir.exists():
        for md in sorted(raw_dir.glob("*.md")):
            try:
                body = md.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue
            if len(body) < 40:
                continue
            parts = re.split(r"\n{2,}", body)
            buf = ""
            idx = 0
            for part in parts:
                if len(buf) + len(part) < 800:
                    buf = f"{buf}\n\n{part}".strip()
                    continue
                if buf:
                    docs.append({
                        "id": f"raw_{md.stem}_{idx}",
                        "text": buf,
                        "title": md.stem.replace("_", " ").title(),
                        "source_type": "policy",
                        "organization": "Knowledge base (raw)",
                        "demo_only": "demo" in md.stem.lower(),
                        "allowed_for_citation": "demo" not in md.stem.lower(),
                    })
                    idx += 1
                buf = part
            if buf:
                docs.append({
                    "id": f"raw_{md.stem}_{idx}",
                    "text": buf,
                    "title": md.stem.replace("_", " ").title(),
                    "source_type": "policy",
                    "organization": "Knowledge base (raw)",
                    "demo_only": "demo" in md.stem.lower(),
                    "allowed_for_citation": "demo" not in md.stem.lower(),
                })

    logger.info("Knowledge RAG corpus: %d documents", len(docs))
    return docs


def _corpus_fingerprint(docs: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for d in docs:
        h.update(d["id"].encode("utf-8", errors="ignore"))
        h.update(b"\0")
        h.update(str(len(d["text"])).encode())
        h.update(b"\n")
    return h.hexdigest()[:16]


def ensure_vector_index(*, force_rebuild: bool = False) -> bool:
    """Build or load the sklearn vector store. Returns True if ready."""
    global _STORE, _BUILD_ATTEMPTED
    if _STORE is not None and not force_rebuild:
        return True
    if _BUILD_ATTEMPTED and not force_rebuild and _STORE is None:
        return False
    _BUILD_ATTEMPTED = True

    try:
        import joblib
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
    except ImportError as exc:
        logger.warning("sklearn/joblib unavailable for RAG: %s", exc)
        return False

    try:
        docs = _load_corpus_documents()
        if not docs:
            logger.warning("No knowledge documents found to index")
            return False

        path = _store_path()
        path.mkdir(parents=True, exist_ok=True)
        meta_path = path / "store_meta.json"
        bundle_path = path / "store.joblib"
        fingerprint = _corpus_fingerprint(docs)

        if (
            not force_rebuild
            and meta_path.exists()
            and bundle_path.exists()
        ):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("fingerprint") == fingerprint:
                    bundle = joblib.load(bundle_path)
                    _STORE = bundle
                    logger.info(
                        "Opened sklearn vector store (%d docs, dim=%s)",
                        len(bundle["docs"]),
                        bundle["embeddings"].shape[1],
                    )
                    return True
            except Exception as exc:
                logger.warning("Failed to load vector store, rebuilding: %s", exc)

        texts = [d["text"] for d in docs]
        vectorizer = TfidfVectorizer(
            max_features=8000,
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)
        n_components = min(EMBED_DIM, max(2, matrix.shape[0] - 1), matrix.shape[1] - 1)
        svd = TruncatedSVD(n_components=n_components, random_state=42)
        embeddings = normalize(svd.fit_transform(matrix))

        bundle = {
            "docs": docs,
            "vectorizer": vectorizer,
            "svd": svd,
            "embeddings": embeddings.astype(np.float32),
        }
        joblib.dump(bundle, bundle_path)
        meta_path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "n_docs": len(docs),
                    "dim": int(embeddings.shape[1]),
                    "backend": "sklearn_tfidf_svd",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        _STORE = bundle
        logger.info(
            "Built sklearn vector store with %d docs (dim=%d)",
            len(docs),
            embeddings.shape[1],
        )
        return True
    except Exception as exc:
        logger.warning("Vector index build/open failed: %s", exc)
        _STORE = None
        return False


# Backwards-compatible alias used by older call sites / docs
def ensure_chroma_index(*, force_rebuild: bool = False) -> bool:
    """Alias: builds the primary file-based vector index (sklearn).

    If AQI_SENTINEL_USE_CHROMA=1, also attempts an optional Chroma collection
    (best-effort; failures are ignored).
    """
    ok = ensure_vector_index(force_rebuild=force_rebuild)
    if os.getenv("AQI_SENTINEL_USE_CHROMA", "").strip() in ("1", "true", "yes"):
        try:
            _try_build_chroma(force_rebuild=force_rebuild)
        except Exception as exc:
            logger.warning("Optional Chroma build skipped: %s", exc)
    return ok


def _try_build_chroma(*, force_rebuild: bool = False) -> None:
    """Optional Chroma path — isolated; must never crash the process caller.

    Note: on some Windows + LangGraph stacks Chroma native code can SIGSEGV.
    Only enable via env when you have verified stability.
    """
    import chromadb
    from chromadb.config import Settings

    path = get_project_root() / "knowledge_base" / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False),
    )
    name = "aqi_sentinel_policy"
    existing = {c.name for c in client.list_collections()}
    if name in existing and not force_rebuild:
        col = client.get_collection(name)
        if col.count() > 0:
            logger.info("Optional Chroma collection ready (%d)", col.count())
            return
    # Build is left to operators; we only verify connectivity here.
    logger.info("Optional Chroma client reachable at %s", path)


def retrieve_knowledge(
    query: str,
    top_k: int = 4,
) -> dict[str, Any]:
    """Retrieve policy/guidance chunks for a query.

    Returns:
      {
        "backend": "sklearn" | "tfidf" | "chroma" | "none",
        "chunks": [{title, text, score, organization, source_type}, ...],
        "context_block": str suitable for LLM injection,
        "used": bool,
      }
    """
    query = (query or "").strip()
    if not query:
        return {"backend": "none", "chunks": [], "context_block": "", "used": False}

    # Primary: sklearn vector store
    if ensure_vector_index():
        try:
            assert _STORE is not None
            from sklearn.preprocessing import normalize

            vectorizer = _STORE["vectorizer"]
            svd = _STORE["svd"]
            embeddings = _STORE["embeddings"]
            docs = _STORE["docs"]

            q_vec = vectorizer.transform([query])
            q_emb = normalize(svd.transform(q_vec)).astype(np.float32)
            # cosine similarity since vectors are L2-normalized
            scores = (embeddings @ q_emb.T).ravel()
            k = min(top_k, len(docs))
            if k > 0:
                top_idx = np.argpartition(-scores, kth=min(k - 1, len(scores) - 1))[:k]
                top_idx = top_idx[np.argsort(-scores[top_idx])]
                chunks = []
                for i in top_idx:
                    score = float(scores[i])
                    if score < 0.02:
                        continue
                    d = docs[int(i)]
                    chunks.append({
                        "title": d.get("title", "Source"),
                        "text": d.get("text", ""),
                        "score": round(score, 4),
                        "organization": d.get("organization", ""),
                        "source_type": d.get("source_type", "policy"),
                        "allowed_for_citation": bool(d.get("allowed_for_citation", True)),
                    })
                if chunks:
                    return {
                        "backend": "sklearn",
                        "chunks": chunks,
                        "context_block": _format_context(chunks),
                        "used": True,
                    }
        except Exception as exc:
            logger.warning("Sklearn vector retrieve failed, falling back: %s", exc)

    # Secondary: existing policy_guidance_service TF-IDF index
    try:
        from backend.app.services.policy_guidance_service import search_policy_guidance

        guidance = search_policy_guidance(query, top_k=top_k)
        results = guidance.get("results") or []
        chunks = []
        for r in results:
            text = r.get("snippet") or r.get("excerpt") or r.get("text") or ""
            chunks.append({
                "title": r.get("title") or r.get("document_id") or "Policy source",
                "text": text,
                "score": float(r.get("score") or 0.0),
                "organization": r.get("organization") or "",
                "source_type": r.get("source_type") or "policy",
                "allowed_for_citation": bool(r.get("allowed_for_citation", False)),
            })
        chunks = [c for c in chunks if c["text"]]
        if chunks:
            return {
                "backend": "tfidf",
                "chunks": chunks,
                "context_block": _format_context(chunks),
                "used": True,
            }
    except Exception as exc:
        logger.warning("TF-IDF knowledge fallback failed: %s", exc)

    return {"backend": "none", "chunks": [], "context_block": "", "used": False}


def _format_context(chunks: list[dict[str, Any]]) -> str:
    parts = [
        "### Official / knowledge-base context (use only if relevant; do not invent citations)",
    ]
    for i, c in enumerate(chunks, 1):
        cite = "citable" if c.get("allowed_for_citation") else "background-only"
        parts.append(
            f"[{i}] ({cite}) {c.get('title', 'Source')} — {c.get('organization', '')}\n"
            f"{c.get('text', '')[:600]}"
        )
    return "\n\n".join(parts)
