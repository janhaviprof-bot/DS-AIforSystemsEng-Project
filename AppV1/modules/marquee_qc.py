from __future__ import annotations

import re

MAX_CORPUS_CHARS = 3000
_ENTITY_RE = re.compile(r"\b[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})*\b")
_TOKEN_RE = re.compile(r"[a-zA-Z]{3,}")
VAGUE_PHRASES = [
    "mixed signals",
    "uncertain outlook",
    "remains to be seen",
    "it is unclear",
    "wait and see",
    "complex situation",
    "ongoing situation",
    "developing story",
]


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _overlap_to_score(overlap: float) -> int:
    if overlap >= 0.40:
        return 5
    if overlap >= 0.30:
        return 4
    if overlap >= 0.20:
        return 3
    if overlap >= 0.10:
        return 2
    return 1


def _ratio_to_score(ratio: float) -> int:
    if ratio >= 0.80:
        return 5
    if ratio >= 0.60:
        return 4
    if ratio >= 0.40:
        return 3
    if ratio >= 0.20:
        return 2
    return 1


def _build_source_corpus(section_packets: list[dict]) -> str:
    chunks: list[str] = []
    for packet in section_packets or []:
        brief = str(packet.get("brief", "") or "").strip()[:300]
        if brief:
            chunks.append(brief)
        headlines = [str(v or "").strip() for v in (packet.get("headlines", []) or [])[:3]]
        chunks.extend(v for v in headlines if v)
        summaries = [str(v or "").strip()[:100] for v in (packet.get("article_summaries", []) or [])[:3]]
        chunks.extend(v for v in summaries if v)
    return " ".join(chunks).lower()[:MAX_CORPUS_CHARS]


def _aggregate_sentiments(section_packets: list[dict]) -> tuple[int, int, int]:
    pos = neg = neu = 0
    for packet in section_packets or []:
        counts = packet.get("sentiment_counts", {}) or {}
        pos += int(counts.get("positive", 0) or 0)
        neg += int(counts.get("negative", 0) or 0)
        neu += int(counts.get("neutral", 0) or 0)
    return pos, neg, neu


def _score_bundle(
    output_text: str,
    workflow: dict,
    source_packets: list[dict],
    *,
    fixed_consistency_score: int | None = None,
) -> dict:
    output_text = str(output_text or "")
    workflow = workflow or {}
    source_corpus = _build_source_corpus(source_packets)
    out_tokens = _tokenize(output_text)
    src_tokens = _tokenize(source_corpus)

    overlap = len(out_tokens & src_tokens) / max(len(out_tokens), 1)
    semantic_score = _overlap_to_score(overlap)

    agent2 = workflow.get("agent2", {}) or {}
    mood_score = int(agent2.get("world_mood_score", 0) or 0)
    pos, neg, neu = _aggregate_sentiments(source_packets)
    total = pos + neg + neu
    if total == 0:
        sentiment_score = 3
    else:
        net_articles = (pos - neg) / total
        net_agent = mood_score / 100
        diff = abs(net_articles - net_agent)
        if diff <= 0.15:
            sentiment_score = 5
        elif diff <= 0.30:
            sentiment_score = 4
        elif diff <= 0.45:
            sentiment_score = 3
        elif diff <= 0.60:
            sentiment_score = 2
        else:
            sentiment_score = 1

    entities = list(dict.fromkeys(e.strip().lower() for e in _ENTITY_RE.findall(output_text)))
    if not entities:
        grounding_score = 3
    else:
        matched = sum(1 for ent in entities if ent in source_corpus)
        grounding_score = _ratio_to_score(matched / len(entities))

    if fixed_consistency_score is None:
        agent1 = workflow.get("agent1", {}) or {}
        agent3 = workflow.get("agent3", {}) or {}
        agreement = str(agent3.get("market_agreement", "mixed") or "mixed").lower().strip()
        if agreement == "aligned" and abs(mood_score) > 20:
            check_a = 5
        elif agreement == "mixed" or mood_score == 0:
            check_a = 3
        elif agreement == "divergent" and abs(mood_score) > 30:
            check_a = 1
        else:
            check_a = 2
        a1_summary = str(agent1.get("cross_section_summary", "") or "")
        a3_insight = str(agent3.get("final_insight", "") or "")
        overlap_b = len(_tokenize(a1_summary) & _tokenize(a3_insight)) / max(len(_tokenize(a3_insight)), 1)
        check_b = _overlap_to_score(overlap_b)
        consistency_score = int(round((check_a + check_b) / 2))
    else:
        consistency_score = int(fixed_consistency_score)

    out_lower = output_text.lower()
    vague_hits = sum(1 for phrase in VAGUE_PHRASES if phrase in out_lower)
    long_tokens = [t for t in out_tokens if len(t) >= 6]
    if vague_hits == 0 and len(entities) >= 2 and len(long_tokens) >= 6:
        specificity_score = 5
    elif vague_hits == 0 and (len(entities) >= 1 or len(long_tokens) >= 4):
        specificity_score = 4
    elif vague_hits == 1:
        specificity_score = 3
    elif vague_hits == 2:
        specificity_score = 2
    else:
        specificity_score = 1

    metrics = {
        "semantic": semantic_score,
        "sentiment": sentiment_score,
        "grounding": grounding_score,
        "consistency": consistency_score,
        "specificity": specificity_score,
    }
    score = round(sum(metrics.values()) / 25 * 100)
    band = "high" if score >= 80 else "moderate" if score >= 60 else "low"
    label = {"high": "High confidence", "moderate": "Moderate", "low": "Low confidence"}[band]
    return {"metrics": metrics, "score": score, "band": band, "label": label}


def evaluate_marquee_quality(output_text: str, workflow: dict, section_packets: list[dict]) -> dict:
    base = _score_bundle(output_text, workflow, section_packets)
    per_section: dict[str, dict] = {}
    for packet in section_packets or []:
        section = str(packet.get("section", "") or "").strip()
        if not section or section == "ALL":
            continue
        per_section[section] = _score_bundle(
            output_text,
            workflow,
            [packet],
            fixed_consistency_score=int(base["metrics"]["consistency"]),
        )
    base["sections"] = per_section
    return base
