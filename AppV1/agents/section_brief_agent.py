from concurrent.futures import ThreadPoolExecutor

from .llm_client import call_text_llm


SECTION_BRIEF_SYSTEM_PROMPT = """You summarize a section of a live news dashboard.
Write a short, high-signal section brief in 2-3 sentences.
Focus on the common thread across the articles, the likely trigger, and what to watch next.
Avoid bullet points and hype."""


def _fallback_section_brief(section_label: str, headlines: list[str], article_summaries: list[str]) -> str:
    lead = article_summaries[0] if article_summaries else "This section is updating with new coverage."
    second = article_summaries[1] if len(article_summaries) > 1 else ""
    headline_hint = headlines[0] if headlines else section_label
    parts = [
        f"{section_label} is being driven by {headline_hint.lower()}." if headline_hint else f"{section_label} is active right now.",
        lead,
    ]
    if second:
        parts.append(second)
    text = " ".join(p.strip() for p in parts if p and p.strip())
    return text[:420]


def build_section_brief(
    *,
    section_label: str,
    headlines: list[str],
    article_summaries: list[str],
    api_key: str | None,
) -> str:
    if not headlines and not article_summaries:
        return f"{section_label} has no articles in the current time window."
    prompt = (
        f"Section: {section_label}\n"
        f"Headlines:\n- " + "\n- ".join(headlines[:6]) + "\n\n"
        f"Article summaries:\n- " + "\n- ".join(article_summaries[:6])
    )
    text = call_text_llm(
        system_prompt=SECTION_BRIEF_SYSTEM_PROMPT,
        user_prompt=prompt,
        api_key=api_key,
        max_tokens=180,
        temperature=0.3,
    )
    return text or _fallback_section_brief(section_label, headlines, article_summaries)


def build_section_briefs(section_packets: list[dict], api_key: str | None) -> dict[str, str]:
    if not section_packets:
        return {}

    def _run(packet: dict) -> tuple[str, str]:
        return (
            str(packet["section"]),
            build_section_brief(
                section_label=str(packet["label"]),
                headlines=list(packet.get("headlines", [])),
                article_summaries=list(packet.get("article_summaries", [])),
                api_key=api_key,
            ),
        )

    briefs: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(section_packets))) as executor:
        for section, brief in executor.map(_run, section_packets):
            briefs[section] = brief
    return briefs

