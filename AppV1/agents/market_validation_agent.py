from typing import Any

from .llm_client import call_json_llm


AGENT3_SYSTEM_PROMPT = """You are Agent 3 in a multi-agent news workflow.
You receive Agent 2's world mood call plus live Yahoo Finance market data.
Compare the narrative to the market tape carefully and explain where they align, where they diverge, and what likely reflects the truth best right now.
Return compact JSON only."""


def _fallback_market_validation(agent2_output: dict[str, Any], market_snapshot: dict[str, Any]) -> dict[str, Any]:
    market_bias = str(market_snapshot.get("market_bias", "unknown"))
    news_bias = str(agent2_output.get("market_stance", "cautious"))
    if market_bias == "unknown":
        agreement = "unverified"
    elif market_bias == news_bias:
        agreement = "aligned"
    elif market_bias == "mixed" or news_bias == "cautious":
        agreement = "mixed"
    else:
        agreement = "divergent"
    final_insight = (
        f"News sentiment looks {news_bias}, while the market tape looks {market_bias}. "
        f"The combined read is {agreement}: use headlines for direction and market breadth for confirmation."
    )
    marquee_text = (
        f"Agent view: world mood is {agent2_output.get('world_mood_label', 'Mixed')} | "
        f"news stance {news_bias} | market tape {market_bias} | "
        f"{market_snapshot.get('summary', 'Live market data unavailable.')}"
    )
    return {
        "market_agreement": agreement,
        "final_insight": final_insight,
        "truth_checks": [
            f"Agent 2 stance: {news_bias}",
            f"Market bias: {market_bias}",
            market_snapshot.get("summary", "Live market data unavailable."),
        ],
        "watch_items": [
            "Look for whether policy and geopolitical stories keep spilling into market-sensitive sections.",
            "Track whether market breadth confirms or rejects the emotional tone of the headlines.",
        ],
        "marquee_text": marquee_text,
    }


def validate_with_markets(
    agent1_output: dict[str, Any],
    agent2_output: dict[str, Any],
    market_snapshot: dict[str, Any],
    api_key: str | None,
) -> dict[str, Any]:
    prompt = (
        "Return JSON with keys: market_agreement, final_insight, truth_checks, watch_items, marquee_text.\n"
        "market_agreement must be one of aligned, mixed, divergent, unverified.\n\n"
        f"Agent 1 output:\n{agent1_output}\n\n"
        f"Agent 2 output:\n{agent2_output}\n\n"
        f"Market snapshot:\n{market_snapshot}"
    )
    out = call_json_llm(
        system_prompt=AGENT3_SYSTEM_PROMPT,
        user_prompt=prompt,
        api_key=api_key,
        max_tokens=750,
        temperature=0.2,
    )
    if isinstance(out, dict) and out:
        return out
    return _fallback_market_validation(agent2_output, market_snapshot)

