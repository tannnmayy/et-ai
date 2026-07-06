from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return path.read_text(encoding="utf-8")
    elif suffix == ".txt":
        return path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(path))
            pages = []
            for page in doc:
                pages.append(page.get_text())
            doc.close()
            return "\n\n".join(pages)
        except ImportError:
            raise RuntimeError("PyMuPDF not installed. Install with: pip install pymupdf")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def _extract_sections(text: str) -> list[dict]:
    lines = text.split("\n")
    sections: list[dict] = []
    current_heading = None
    current_level = 0
    current_content: list[str] = []

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            if current_content and current_heading is not None:
                sections.append({
                    "heading": current_heading,
                    "level": current_level,
                    "content": "\n".join(current_content).strip(),
                })
            current_heading = heading_match.group(2).strip()
            current_level = len(heading_match.group(1))
            current_content = []
        else:
            current_content.append(line)

    if current_content and current_heading is not None:
        sections.append({
            "heading": current_heading,
            "level": current_level,
            "content": "\n".join(current_content).strip(),
        })

    if not sections:
        sections.append({"heading": None, "level": 0, "content": text.strip()})

    return sections


def _chunk_text(text: str, section_heading: str | None, page_number: int | None) -> list[dict]:
    chunks: list[dict] = []
    start = 0
    text_len = len(text)

    if text_len == 0:
        return chunks

    while start < text_len:
        end = min(start + CHUNK_SIZE, text_len)
        if end < text_len:
            break_point = text.rfind("\n\n", start, end)
            if break_point > start + CHUNK_SIZE // 2:
                end = break_point
            else:
                break_point = text.rfind(". ", start, end)
                if break_point > start + CHUNK_SIZE // 2:
                    end = break_point + 1

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "section_heading": section_heading,
                "page_number": page_number,
            })

        start = end - CHUNK_OVERLAP if end < text_len else text_len

    return chunks


def _validate_metadata(doc: dict, kb_raw: Path) -> list[str]:
    errors: list[str] = []
    required = ["document_id", "title", "organization", "source_type", "jurisdiction", "local_path", "sha256", "language", "demo_only", "allowed_for_citation"]

    for field in required:
        if field not in doc:
            errors.append(f"Missing required field: {field}")

    source_types = ["policy", "health_guidance", "standard", "advisory"]
    if "source_type" in doc and doc["source_type"] not in source_types:
        errors.append(f"Invalid source_type: {doc['source_type']}")

    jurisdictions = ["India", "Karnataka", "Bengaluru", "Global"]
    if "jurisdiction" in doc and doc["jurisdiction"] not in jurisdictions:
        errors.append(f"Invalid jurisdiction: {doc['jurisdiction']}")

    languages = ["en", "hi", "kn"]
    if "language" in doc and doc["language"] not in languages:
        errors.append(f"Invalid language: {doc['language']}")

    if "local_path" in doc:
        file_path = kb_raw / doc["local_path"]
        if not file_path.exists():
            errors.append(f"File not found: {doc['local_path']}")

    return errors


def build_index(
    project_root: str | Path | None = None,
    kb_dir: str | Path | None = None,
) -> dict[str, Any]:
    if project_root is None:
        from backend.app.config import get_project_root
        project_root = get_project_root()
    project_root = Path(project_root)

    if kb_dir is None:
        from backend.app.config import KNOWLEDGE_BASE_DIR
        kb_dir = project_root / KNOWLEDGE_BASE_DIR
    kb_dir = Path(kb_dir)

    kb_raw = kb_dir / "raw"
    manifests_dir = kb_dir / "manifests"
    processed_dir = kb_dir / "processed"
    indexes_dir = kb_dir / "indexes"
    reports_dir = kb_dir / "reports"

    manifest_path = manifests_dir / "corpus_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents", [])

    if not documents:
        raise ValueError("Manifest contains no documents")

    errors: list[str] = []
    validated_docs: list[dict] = []
    for doc in documents:
        doc_errors = _validate_metadata(doc, kb_raw)
        if doc_errors:
            errors.extend([f"{doc.get('document_id', 'unknown')}: {e}" for e in doc_errors])
        else:
            validated_docs.append(doc)

    if errors:
        for e in errors:
            logger.error("Metadata error: %s", e)

    total_docs = len(validated_docs)
    eligible_docs = [d for d in validated_docs if d.get("allowed_for_citation") and not d.get("demo_only")]
    demo_docs = [d for d in validated_docs if d.get("demo_only")]

    all_chunks: list[dict] = []
    extraction_failures: list[str] = []

    for doc in validated_docs:
        doc_id = doc["document_id"]
        file_path = kb_raw / doc["local_path"]
        try:
            text = _extract_text(file_path)
            actual_hash = _compute_sha256(file_path)
            if actual_hash != doc.get("sha256", ""):
                logger.warning("Hash mismatch for %s: file=%s manifest=%s", doc_id, actual_hash, doc.get("sha256"))
                doc["sha256_actual"] = actual_hash

            sections = _extract_sections(text)
            chunk_index = 0
            for section in sections:
                chunks = _chunk_text(section["content"], section["heading"], None)
                for chunk in chunks:
                    chunk_id = f"{doc_id}_chunk_{chunk_index:04d}"
                    char_count = len(chunk["text"])
                    all_chunks.append({
                        "chunk_id": chunk_id,
                        "document_id": doc_id,
                        "text": chunk["text"],
                        "page_number": chunk["page_number"],
                        "section_heading": chunk["section_heading"],
                        "chunk_index": chunk_index,
                        "character_count": char_count,
                        "title": doc.get("title", ""),
                        "organization": doc.get("organization", ""),
                        "source_type": doc.get("source_type", ""),
                        "jurisdiction": doc.get("jurisdiction", ""),
                        "publication_date": doc.get("publication_date"),
                        "source_url": doc.get("source_url"),
                        "demo_only": doc.get("demo_only", False),
                        "allowed_for_citation": doc.get("allowed_for_citation", False),
                    })
                    chunk_index += 1
        except Exception as e:
            extraction_failures.append(f"{doc_id}: {e}")
            logger.error("Extraction failed for %s: %s", doc_id, e)

    processed_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = processed_dir / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    total_chunks = len(all_chunks)

    from backend.app.config import KNOWLEDGE_RETRIEVAL_MODE

    if KNOWLEDGE_RETRIEVAL_MODE == "semantic":
        retrieval_mode = _build_semantic_index(all_chunks, indexes_dir)
    else:
        retrieval_mode = _build_lexical_index(all_chunks, indexes_dir)

    index_metadata = {
        "index_built_at": datetime.now(tz=timezone.utc).isoformat(),
        "retrieval_mode": retrieval_mode,
        "total_documents": total_docs,
        "eligible_citation_documents": len(eligible_docs),
        "excluded_demo_documents": len(demo_docs),
        "total_chunks": total_chunks,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "extraction_failures": extraction_failures,
    }

    indexes_dir.mkdir(parents=True, exist_ok=True)
    index_meta_path = indexes_dir / "index_metadata.json"
    index_meta_path.write_text(json.dumps(index_metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = reports_dir / "index_report.json"
    report_json_path.write_text(json.dumps(index_metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    report_md_path = reports_dir / "index_report.md"
    md_lines = [
        "# Knowledge Base Index Report",
        "",
        f"- **Build time:** {index_metadata['index_built_at']}",
        f"- **Retrieval mode:** {retrieval_mode}",
        f"- **Total documents:** {total_docs}",
        f"- **Eligible citation documents:** {len(eligible_docs)}",
        f"- **Demo-only documents:** {len(demo_docs)}",
        f"- **Total chunks:** {total_chunks}",
        f"- **Chunk size:** {CHUNK_SIZE} chars",
        f"- **Chunk overlap:** {CHUNK_OVERLAP} chars",
    ]
    if extraction_failures:
        md_lines.append("")
        md_lines.append("## Extraction Failures")
        for f in extraction_failures:
            md_lines.append(f"- {f}")

    report_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    logger.info("Index built successfully. %d chunks from %d documents.", total_chunks, total_docs)
    return index_metadata


def _build_lexical_index(chunks: list[dict], indexes_dir: Path) -> str:
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts = [c["text"] for c in chunks]
    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        max_features=50000,
        stop_words="english",
    )
    tfidf_matrix = vectorizer.fit_transform(texts)

    import joblib
    indexes_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, indexes_dir / "tfidf_vectorizer.joblib")
    joblib.dump(tfidf_matrix, indexes_dir / "tfidf_matrix.joblib")
    joblib.dump(chunks, indexes_dir / "chunk_data.joblib")

    feature_count = len(vectorizer.get_feature_names_out())
    logger.info("Lexical index built: %d features, %d chunks", feature_count, len(chunks))
    return "lexical"


def _build_semantic_index(chunks: list[dict], indexes_dir: Path) -> str:
    try:
        from sentence_transformers import SentenceTransformer

        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        model = SentenceTransformer(model_name)
        texts = [c["text"] for c in chunks]
        embeddings = model.encode(texts, show_progress_bar=False)

        import joblib
        import numpy as np

        indexes_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, indexes_dir / "embedding_model.joblib")
        np.save(str(indexes_dir / "embeddings.npy"), embeddings)
        joblib.dump(chunks, indexes_dir / "chunk_data.joblib")

        logger.info("Semantic index built: %d chunks, dim=%d", len(chunks), embeddings.shape[1])
        return "semantic"
    except Exception as e:
        logger.warning("Semantic index build failed: %s. Falling back to lexical.", e)
        return _build_lexical_index(chunks, indexes_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build knowledge base index")
    parser.add_argument("--project-root", type=str, default=None, help="Project root directory")
    parser.add_argument("--kb-dir", type=str, default=None, help="Knowledge base directory")
    args = parser.parse_args()
    build_index(project_root=args.project_root, kb_dir=args.kb_dir)


if __name__ == "__main__":
    main()
