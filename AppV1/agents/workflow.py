from datetime import datetime
from typing import Any

from .cross_section_agent import analyze_cross_section_links
from .market_data import fetch_market_snapshot
from .market_validation_agent import validate_with_markets
from .output_qc import (
    compute_composite_evidence_score,
    validate_workflow_outputs,
    workflow_confidence_heuristic,
)
from .section_brief_agent import build_section_briefs
from .world_sentiment_agent import evaluate_world_sentiment
from modules.marquee_qc import evaluate_marquee_quality
from modules.marquee_surface import marquee_surface_text

SECTION_LABELS = {
    "ALL": "All News",
    "business": "Business",
    "arts": "Arts",
    "technology": "Technology",
    "world": "World",
    "politics": "Politics",
}

WORKFLOW_SECTIONS = ["ALL", "business", "arts", "technology", "world", "politics"]
AGENT_ANALYSIS_SECTIONS = ["business", "arts", "technology", "world", "politics"]


def generate_section_briefs(section_packets: list[dict[str, Any]], api_key: str | None) -> dict[str, str]:
    return build_section_briefs(section_packets, api_key)


def run_multi_agent_workflow(section_packets: list[dict[str, Any]], api_key: str | None) -> dict[str, Any]:
    packets_for_agents = [
        packet for packet in section_packets if str(packet.get("section")) in AGENT_ANALYSIS_SECTIONS
    ]
    agent1, src1 = analyze_cross_section_links(packets_for_agents, api_key)
    agent2, src2 = evaluate_world_sentiment(agent1, packets_for_agents, api_key)
    market_snapshot = fetch_market_snapshot()
    agent3, src3 = validate_with_markets(agent1, agent2, market_snapshot, api_key)
    provenance = {"agent1": src1, "agent2": src2, "agent3": src3}
    workflow: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "agent1": agent1,
        "agent2": agent2,
        "agent3": agent3,
        "market_snapshot": market_snapshot,
        "marquee_text": agent3.get("marquee_text") or agent3.get("final_insight") or "Agent insight is updating.",
        "provenance": provenance,
    }
    output_text = marquee_surface_text(workflow)
    workflow["marquee_qc"] = evaluate_marquee_quality(output_text, workflow, section_packets)
    qc_report = validate_workflow_outputs(agent1, agent2, agent3, market_snapshot, provenance)
    workflow["qc_report"] = qc_report.to_dict()
    workflow["composite_evidence_score"] = compute_composite_evidence_score(
        qc_report,
        provenance,
        workflow.get("marquee_qc"),
        workflow_confidence_heuristic(agent1, agent3, market_snapshot),
    )
    return workflow
