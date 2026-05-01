from typing import Any

from .llm_client import call_json_llm


AGENT_SYSTEM_PROMPT = """You are Agent 1 in a news intelligence workflow.
You compare section briefs from business, arts, technology, world, and politics.
Find cross-section links, likely trigger events, and which stories are propagating into other sections.
Return compact JSON only."""


def _fallback_connections(section_packets: list[dict[str, Any]]) -> dict[str, Any]:
    active_sections = [p["label"] for p in section_packets if p.get("headlines")]
    connections = []
    if len(active_sections) >= 2:
        connections.append(
            {
                "theme": "Policy, markets, and public response are moving together",
                "sections": active_sections[:3],
                "why_it_matters": "The same macro events are showing up across multiple desks, which usually signals a broader narrative rather than an isolated headline.",
                "trigger": "A cluster of fast-moving top stories in the current news window.",
            }
        )
    return {
        "headline": "Cross-section links detected across the current news cycle.",
        "cross_section_summary": "Multiple desks are reacting to the same short list of events, suggesting the news cycle is being driven by shared triggers rather than isolated stories.",
        "connections": connections,
        "event_chain": [
            "A major event or policy update breaks.",
            "Political and world coverage frame the cause and stakes.",
            "Business and technology coverage react through market, company, or platform impacts.",
        ],
        "section_takeaways": [
            {
                "section": str(packet["section"]),
                "summary": str(packet.get("brief", "")),
            }
            for packet in section_packets
        ],
    }


def analyze_cross_section_links(
    section_packets: list[dict[str, Any]], api_key: str | None
) -> tuple[dict[str, Any], str]:
    payload_lines = []
    for packet in section_packets:
        payload_lines.append(
            "\n".join(
                [
                    f"Section: {packet['label']}",
                    f"Brief: {packet.get('brief', '')}",
                    "Headlines:",
                    *[f"- {h}" for h in packet.get("headlines", [])[:5]],
                    f"Sentiment counts: {packet.get('sentiment_counts', {})}",
                ]
            )
        )
    prompt = (
        "Analyze these section briefs and return JSON with keys: "
        "headline, cross_section_summary, connections, event_chain, section_takeaways. "
        "Each item in connections must have theme, sections, why_it_matters, trigger. "
        "Each item in section_takeaways must have section and summary.\n\n"
        + "\n\n".join(payload_lines)
    )
    out = call_json_llm(
        system_prompt=AGENT_SYSTEM_PROMPT,
        user_prompt=prompt,
        api_key=api_key,
        max_tokens=900,
        temperature=0.2,
    )
    if isinstance(out, dict) and out:
        return out, "llm"
    return _fallback_connections(section_packets), "fallback"

