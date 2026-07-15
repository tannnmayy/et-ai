"""Dense RAG over knowledge_base/ using sentence-transformers + FAISS.

Primary path
------------
* Embeddings: ``sentence-transformers`` model (default ``all-MiniLM-L6-v2``)
* Index: FAISS ``IndexFlatIP`` (cosine via L2-normalized vectors)
* Persist: ``knowledge_base/vector_store/faiss.index`` + ``faiss_meta.json``

Fallback chain (never hard-fails)
---------------------------------
1. FAISS dense retrieval
2. Legacy sklearn TF-IDF/SVD store (``knowledge_rag_service``)
3. Policy guidance lexical TF-IDF index

Chunking
--------
Source text is re-chunked to ~500–800 characters with overlap so long
policy PDFs produce retrieval-friendly passages.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
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
DEFAULT_MODEL = os.getenv("AQI_SENTINEL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("AQI_SENTINEL_RAG_CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.getenv("AQI_SENTINEL_RAG_CHUNK_OVERLAP", "120"))
MIN_CHUNK_CHARS = 40

_LOCK = threading.RLock()
_INDEX = None  # faiss.Index
_META: list[dict[str, Any]] | None = None
_MODEL = None
_MODEL_NAME: str | None = None
_BUILD_ATTEMPTED = False
_READY = False

# Lightweight query→result cache for retrieve_relevant_context
_RETRIEVE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_RETRIEVE_CACHE_TTL = int(os.getenv("AQI_SENTINEL_RAG_CACHE_TTL", str(10 * 60)))


def _store_dir() -> Path:
    return get_project_root() / STORE_DIR_REL


def _chunks_path() -> Path:
    return get_project_root() / KNOWLEDGE_BASE_DIR / KNOWLEDGE_CHUNKS_PATH


def _index_path() -> Path:
    return _store_dir() / "faiss.index"


def _meta_path() -> Path:
    return _store_dir() / "faiss_meta.json"


def _fingerprint_path() -> Path:
    return _store_dir() / "faiss_fingerprint.json"


# ---------------------------------------------------------------------------
# Corpus loading + chunking
# ---------------------------------------------------------------------------


def _split_with_overlap(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Character-window chunking with sentence-friendly breaks when possible."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= size:
        return [text] if len(text) >= MIN_CHUNK_CHARS else []

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # Prefer breaking on sentence / clause boundaries
            window = text[start:end]
            break_at = max(window.rfind(". "), window.rfind("; "), window.rfind("\n"))
            if break_at > size // 3:
                end = start + break_at + 1
        piece = text[start:end].strip()
        if len(piece) >= MIN_CHUNK_CHARS:
            chunks.append(piece)
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def _load_raw_documents() -> list[dict[str, Any]]:
    """Load source docs from processed chunks + raw markdown."""
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
                if len(text) < MIN_CHUNK_CHARS:
                    continue
                docs.append({
                    "source_id": row.get("chunk_id") or row.get("document_id") or "",
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
            if len(body) < MIN_CHUNK_CHARS:
                continue
            docs.append({
                "source_id": f"raw_{md.stem}",
                "text": body,
                "title": md.stem.replace("_", " ").title(),
                "source_type": "policy",
                "organization": "Knowledge base (raw)",
                "demo_only": "demo" in md.stem.lower(),
                "allowed_for_citation": "demo" not in md.stem.lower(),
            })
    return docs


def build_corpus_chunks() -> list[dict[str, Any]]:
    """Expand source docs into overlapping retrieval chunks."""
    out: list[dict[str, Any]] = []
    for doc in _load_raw_documents():
        pieces = _split_with_overlap(doc["text"])
        for i, piece in enumerate(pieces):
            cid = hashlib.md5(f"{doc['source_id']}:{i}:{piece[:80]}".encode()).hexdigest()[:16]
            out.append({
                "id": cid,
                "text": piece,
                "title": doc["title"],
                "source_type": doc["source_type"],
                "organization": doc["organization"],
                "demo_only": doc["demo_only"],
                "allowed_for_citation": doc["allowed_for_citation"],
                "chunk_index": i,
            })
    logger.info("RAG corpus: %d chunks from knowledge_base", len(out))
    return out


def _corpus_fingerprint(chunks: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    h.update(DEFAULT_MODEL.encode())
    h.update(f"|{CHUNK_SIZE}|{CHUNK_OVERLAP}|".encode())
    for c in chunks:
        h.update(c["id"].encode())
        h.update(str(len(c["text"])).encode())
    return h.hexdigest()[:20]


# ---------------------------------------------------------------------------
# Model + index lifecycle
# ---------------------------------------------------------------------------


def _get_model():
    global _MODEL, _MODEL_NAME
    if _MODEL is not None:
        return _MODEL
    from sentence_transformers import SentenceTransformer

    model_name = DEFAULT_MODEL
    logger.info("Loading embedding model: %s", model_name)
    _MODEL = SentenceTransformer(model_name)
    _MODEL_NAME = model_name
    return _MODEL


def _embed_texts(texts: list[str], *, show_progress: bool = False) -> np.ndarray:
    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return np.asarray(vectors, dtype=np.float32)


def ensure_faiss_index(*, force_rebuild: bool = False) -> bool:
    """Build or load the FAISS index. Returns True if dense RAG is ready."""
    global _INDEX, _META, _BUILD_ATTEMPTED, _READY

    with _LOCK:
        if _READY and _INDEX is not None and _META is not None and not force_rebuild:
            return True
        if _BUILD_ATTEMPTED and not force_rebuild and not _READY:
            return False
        _BUILD_ATTEMPTED = True

        try:
            import faiss  # type: ignore
        except ImportError:
            logger.warning("faiss not installed — dense RAG disabled (pip install faiss-cpu)")
            _READY = False
            return False

        try:
            chunks = build_corpus_chunks()
            if not chunks:
                logger.warning("No knowledge chunks available for FAISS index")
                _READY = False
                return False

            fingerprint = _corpus_fingerprint(chunks)
            store = _store_dir()
            store.mkdir(parents=True, exist_ok=True)
            fp_path = _fingerprint_path()
            idx_path = _index_path()
            meta_path = _meta_path()

            if (
                not force_rebuild
                and idx_path.exists()
                and meta_path.exists()
                and fp_path.exists()
            ):
                try:
                    saved_fp = json.loads(fp_path.read_text(encoding="utf-8")).get("fingerprint")
                    if saved_fp == fingerprint:
                        _INDEX = faiss.read_index(str(idx_path))
                        payload = json.loads(meta_path.read_text(encoding="utf-8"))
                        _META = payload.get("chunks") or []
                        if _META and _INDEX.ntotal == len(_META):
                            _READY = True
                            logger.info(
                                "Loaded FAISS index (%d vectors, model=%s)",
                                _INDEX.ntotal,
                                payload.get("model", DEFAULT_MODEL),
                            )
                            return True
                except Exception as exc:
                    logger.warning("Failed to load FAISS index, rebuilding: %s", exc)

            # Build
            texts = [c["text"] for c in chunks]
            logger.info("Embedding %d chunks with %s …", len(texts), DEFAULT_MODEL)
            vectors = _embed_texts(texts, show_progress=False)
            dim = int(vectors.shape[1])
            index = faiss.IndexFlatIP(dim)
            index.add(vectors)
            faiss.write_index(index, str(idx_path))
            meta_path.write_text(
                json.dumps(
                    {
                        "model": DEFAULT_MODEL,
                        "dim": dim,
                        "n_chunks": len(chunks),
                        "chunk_size": CHUNK_SIZE,
                        "chunk_overlap": CHUNK_OVERLAP,
                        "chunks": chunks,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            fp_path.write_text(
                json.dumps({"fingerprint": fingerprint, "model": DEFAULT_MODEL}, indent=2),
                encoding="utf-8",
            )
            _INDEX = index
            _META = chunks
            _READY = True
            logger.info("Built FAISS index with %d vectors (dim=%d)", index.ntotal, dim)
            return True
        except Exception as exc:
            logger.warning("FAISS index build failed: %s", exc)
            _INDEX = None
            _META = None
            _READY = False
            return False


def _format_context(chunks: list[dict[str, Any]]) -> str:
    parts = [
        "### Official / knowledge-base context "
        "(use only if relevant; quote carefully; do not invent citations)",
    ]
    for i, c in enumerate(chunks, 1):
        cite = "citable" if c.get("allowed_for_citation") else "background-only"
        parts.append(
            f"[{i}] ({cite}) {c.get('title', 'Source')} — {c.get('organization', '')}\n"
            f"{c.get('text', '')[:700]}"
        )
    return "\n\n".join(parts)


def _faiss_retrieve(query: str, top_k: int) -> dict[str, Any] | None:
    if not ensure_faiss_index():
        return None
    assert _INDEX is not None and _META is not None
    q = _embed_texts([query])
    k = min(top_k, len(_META))
    if k <= 0:
        return None
    scores, indices = _INDEX.search(q, k)
    chunks: list[dict[str, Any]] = []
    for score, idx in zip(scores[0].tolist(), indices[0].tolist()):
        if idx < 0 or idx >= len(_META):
            continue
        # Inner-product on normalized vectors ≈ cosine similarity in [-1, 1]
        if float(score) < 0.15:
            continue
        m = _META[idx]
        chunks.append({
            "title": m.get("title", "Source"),
            "text": m.get("text", ""),
            "score": round(float(score), 4),
            "organization": m.get("organization", ""),
            "source_type": m.get("source_type", "policy"),
            "allowed_for_citation": bool(m.get("allowed_for_citation", True)),
        })
    if not chunks:
        return None
    return {
        "backend": "faiss",
        "chunks": chunks,
        "context_block": _format_context(chunks),
        "used": True,
        "model": _MODEL_NAME or DEFAULT_MODEL,
    }


def retrieve_relevant_context(query: str, top_k: int = 5) -> dict[str, Any]:
    """Retrieve policy/guidance context for a user query.

    Returns:
      {
        "backend": "faiss" | "sklearn" | "tfidf" | "none",
        "chunks": [...],
        "context_block": str,
        "used": bool,
        "model": optional str,
      }
    """
    query = (query or "").strip()
    if not query:
        return {"backend": "none", "chunks": [], "context_block": "", "used": False}

    cache_key = hashlib.sha256(f"{query}|{top_k}".encode()).hexdigest()
    hit = _RETRIEVE_CACHE.get(cache_key)
    if hit and time.time() - hit[0] <= _RETRIEVE_CACHE_TTL:
        return hit[1]

    result: dict[str, Any] | None = None

    # 1) Dense FAISS
    try:
        result = _faiss_retrieve(query, top_k=top_k)
    except Exception as exc:
        logger.warning("FAISS retrieve failed: %s", exc)
        result = None

    # 2) Legacy sklearn / knowledge_rag_service
    if not result:
        try:
            from backend.app.services.knowledge_rag_service import retrieve_knowledge

            legacy = retrieve_knowledge(query, top_k=top_k)
            if legacy.get("used"):
                result = legacy
        except Exception as exc:
            logger.warning("Sklearn RAG fallback failed: %s", exc)

    # 3) Policy guidance lexical index
    if not result:
        try:
            from backend.app.services.policy_guidance_service import search_policy_guidance

            guidance = search_policy_guidance(query, top_k=top_k)
            rows = guidance.get("results") or []
            chunks = []
            for r in rows:
                text = r.get("snippet") or r.get("excerpt") or r.get("text") or ""
                if not text:
                    continue
                chunks.append({
                    "title": r.get("title") or "Policy source",
                    "text": text,
                    "score": float(r.get("score") or 0.0),
                    "organization": r.get("organization") or "",
                    "source_type": r.get("source_type") or "policy",
                    "allowed_for_citation": bool(r.get("allowed_for_citation", False)),
                })
            if chunks:
                result = {
                    "backend": "tfidf",
                    "chunks": chunks,
                    "context_block": _format_context(chunks),
                    "used": True,
                }
        except Exception as exc:
            logger.warning("TF-IDF policy fallback failed: %s", exc)

    if not result:
        result = {"backend": "none", "chunks": [], "context_block": "", "used": False}

    _RETRIEVE_CACHE[cache_key] = (time.time(), result)
    if len(_RETRIEVE_CACHE) > 256:
        oldest = sorted(_RETRIEVE_CACHE.items(), key=lambda kv: kv[1][0])[:64]
        for k, _ in oldest:
            _RETRIEVE_CACHE.pop(k, None)
    return result


# Back-compat alias used by older call sites
def retrieve_knowledge(query: str, top_k: int = 4) -> dict[str, Any]:
    return retrieve_relevant_context(query, top_k=top_k)


def warm_rag_index() -> dict[str, Any]:
    """Ensure the FAISS index is built/loaded (for prefetch / startup)."""
    ok = ensure_faiss_index()
    return {
        "ready": ok,
        "backend": "faiss" if ok else "fallback",
        "n_vectors": int(_INDEX.ntotal) if ok and _INDEX is not None else 0,
        "model": DEFAULT_MODEL if ok else None,
    }
