"""One-off smoke test for Copilot multi-key + RAG + routing. Not part of CI."""
from __future__ import annotations

import sys
import traceback


def main() -> int:
    try:
        from backend.app.services.knowledge_rag_service import ensure_chroma_index, retrieve_knowledge
        from backend.app.agents.llm_provider import get_llm_provider
        from backend.app.agents.orchestrator import run_orchestrator

        print("=== keys ===", flush=True)
        llm = get_llm_provider()
        print(f"keys={len(llm._gemini_keys)} providers={llm._providers} available={llm.is_available}", flush=True)

        print("=== rag ===", flush=True)
        print(f"chroma={ensure_chroma_index()}", flush=True)
        rag = retrieve_knowledge("CPCB construction dust control Karnataka", top_k=3)
        print(f"backend={rag['backend']} n={len(rag['chunks'])}", flush=True)
        if rag["chunks"]:
            print(f"title0={rag['chunks'][0].get('title')}", flush=True)

        print("=== orchestrator policy ===", flush=True)
        resp = run_orchestrator(
            query="What does CPCB say about construction dust control?",
            city="bengaluru",
        )
        print(f"intent={resp['intent']}", flush=True)
        print(f"agent={resp['selected_agent']}", flush=True)
        print(f"mode={resp['llm_mode']}", flush=True)
        print(f"fallback={resp['fallback_used']}", flush=True)
        print(f"answer={(resp.get('answer') or '')[:500]}", flush=True)
        at = resp.get("audit_trail") or {}
        print(
            f"kb={at.get('knowledge_base_used')} backend={at.get('knowledge_backend')} "
            f"provider={at.get('llm_provider_used')} key={at.get('gemini_key_index')}",
            flush=True,
        )
        print(f"types={[t.get('type') for t in (at.get('reasoning_trace') or [])]}", flush=True)

        print("=== deep mode ===", flush=True)
        deep = run_orchestrator(
            query="Compare Peenya air quality risk with city briefing and policy dust rules",
            city="bengaluru",
            force_dynamic_planning=True,
        )
        print(f"deep_agent={deep['selected_agent']} mode={deep['llm_mode']} fallback={deep['fallback_used']}", flush=True)
        print(f"deep_answer={(deep.get('answer') or '')[:300]}", flush=True)
        dat = deep.get("audit_trail") or {}
        print(f"deep_types={[t.get('type') for t in (dat.get('reasoning_trace') or [])]}", flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
