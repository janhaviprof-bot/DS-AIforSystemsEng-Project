from typing import Any

from .llm_client import call_json_llm


AGENT_SYSTEM_PROMPT = """You are Agent 2 in a multi-agent news workflow.
You receive Agent 1 cross-section insights plus sentiment counts from the feed.
Judge the overall world mood, give it a score, decide whether the news backdrop feels bullish, bearish, cautious, or constructive, and explain why.
Keep the output sharp and dashboard-friendly.
The description must be one short paragraph of at most 2 sentences.
The reasoning field must be a JSON array with 2 or 3 short bullet-style strings, not one long paragraph.
Return compact JSON only."""


def _fallback_world_sentiment(agent1_output: dict[str, Any], section_packets: list[dict[str, Any]]) -> dict[str, Any]:
    positive = 0
    negative = 0
    neutral = 0
    for packet in section_packets:
        counts = packet.get("sentiment_counts", {})
        positive += int(counts.get("positive", 0))
        negative += int(counts.get("negative", 0))
        neutral += int(counts.get("neutral", 0))
    total = max(1, positive + negative + neutral)
    score = round(((positive - negative) / total) * 100)
    if score >= 20:
        mood = "Constructive"
        stance = "bullish"
    elif score <= -20:
        mood = "Fragile"
        stance = "bearish"
    else:
        mood = "Mixed"
        stance = "cautious"
    return {
        "world_mood_label": mood,
        "world_mood_score": score,
        "market_stance": stance,
        "description": agent1_output.get("cross_section_summary", "The news cycle is mixed."),
        "reasoning": [
            f"Positive items: {positive}",
            f"Negative items: {negative}",
            f"Neutral items: {neutral}",
        ],
    }


def evaluate_world_sentiment(
    agent1_output: dict[str, Any],
    section_packets: list[dict[str, Any]],
    api_key: str | None,
) -> dict[str, Any]:
    prompt = (
        "Return JSON with keys: world_mood_label, world_mood_score, market_stance, description, reasoning.\n"
        "world_mood_score should be an integer from -100 to 100.\n\n"
        "Allowed world_mood_label values: Optimistic, Constructive, Mixed, Cautious, Fragile.\n"
        "Allowed market_stance values: bullish, constructive, cautious, bearish.\n"
        "reasoning must be an array of 2-3 concise strings.\n\n"
        f"Agent 1 output:\n{agent1_output}\n\n"
        f"Section packets:\n{section_packets}"
    )
    out = call_json_llm(
        system_prompt=AGENT_SYSTEM_PROMPT,
        user_prompt=prompt,
        api_key=api_key,
        max_tokens=650,
        temperature=0.2,
    )
    if isinstance(out, dict) and out:
        return out
    return _fallback_world_sentiment(agent1_output, section_packets)
