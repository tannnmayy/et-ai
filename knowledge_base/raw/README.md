# Knowledge Base Raw Documents

Place official policy and health guidance documents in this directory.

Supported formats: `.pdf`, `.txt`, `.md`

## Adding a Document

1. Place the file in this directory.
2. Register it in `../manifests/corpus_manifest.json` with metadata.
3. Run `python -m pipeline.build_knowledge_index` to rebuild the index.

## Important Rules

- Documents must be official and traceable to a source organization.
- Set `allowed_for_citation: true` only for verified official documents.
- Set `demo_only: true` for test/development documents.
- Demo documents will never appear as official citations in API responses.
- Do not commit copyrighted material without permission.
