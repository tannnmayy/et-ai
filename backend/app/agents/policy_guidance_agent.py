from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.state import AgentState
from backend.app.agents.tools import tool_search_policy_guidance

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_search_policy_guidance"]


def run_policy_guidance_agent(state: AgentState, audit: AuditTrail) -> None:
    query = state.user_query
    city = state.city

    guidance_data = tool_search_policy_guidance(query, city=city, top_k=state.top_k)
    audit.record_tool_call(
        "tool_search_policy_guidance",
        {"query": query, "city": city, "top_k": state.top_k},
        "_tool_error" not in guidance_data,
    )

    if "_tool_error" in guidance_data:
        state.warnings.append(f"Policy guidance tool error: {guidance_data['_tool_error']}")
        audit.add_warning(f"Policy guidance tool error: {guidance_data['_tool_error']}")
        state.response = f"Policy guidance unavailable: {guidance_data['_tool_error']}"
        state.structured_data = guidance_data
        return

    results = guidance_data.get("results", [])
    retrieval_mode = guidance_data.get("retrieval_mode", "unknown")
    no_authoritative = guidance_data.get("no_authoritative_result", False)

    if no_authoritative or not results:
        answer = (
            "I searched the local curated guidance corpus but did not find "
            "a sufficiently relevant authoritative source for your query. "
            "The corpus currently contains demo documents that are not eligible for citation. "
            "Add official documents to knowledge_base/raw/ and rebuild the index to enable citations."
        )
        if guidance_data.get("warnings"):
            answer += "\n\n" + "\n".join(guidance_data["warnings"])
    else:
        lines = [f"Found {len(results)} relevant passage(s) from the guidance corpus:"]
        for r in results:
            label = r.get("citation_label", f"[{r['rank']}]")
            title = r.get("title", "Untitled")
            org = r.get("organization", "")
            excerpt = r.get("excerpt", "")[:200]
            lines.append(f"\n{label} {title}")
            if org:
                lines.append(f"   Source: {org}")
            lines.append(f"   {excerpt}")
        lines.append(f"\nRetrieval mode: {retrieval_mode}")
        lines.append("\nRetrieved passages support general guidance and do not prove station-level pollution causes.")
        answer = "\n".join(lines)

    state.response = answer
    state.structured_data = guidance_data
    state.tool_results = {"policy_guidance": guidance_data}
