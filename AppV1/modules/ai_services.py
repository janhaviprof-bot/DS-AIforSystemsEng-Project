# ai_services.py - OpenAI sentiment and summary generation (order-safe, logged, shared client)

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import httpx

from config import OPENAI_MODEL

logger = logging.getLogger(__name__)

BATCH_SIZE = 10  # Titles per sentiment API call
MAX_SENTIMENT_WORKERS = 3  # Parallel batch requests
MAX_SUMMARY_WORKERS = 3  # Reduced from 6 for safer concurrency

_missing_key_warned = False  # Ensure we only log missing-key message once


def _parse_sentiment_response(text: str, n_expected: int) -> list[str]:
    """Parse batch sentiment response. Handles numbered lines, commas, newlines."""
    valid = {"positive", "negative", "neutral"}
    result = []
    for part in text.replace(",", "\n").split():
        w = part.lower().strip(".;:)")
        if w in valid:
            result.append(w)
        elif len(result) < n_expected and any(v in w for v in valid):
            for v in valid:
                if v in w:
                    result.append(v)
                    break
    while len(result) < n_expected:
        result.append("neutral")
    return result[:n_expected]


def get_sentiments_batch(titles: list[str], api_key: Optional[str]) -> list[str]:
    """Get sentiment for multiple titles in one API call."""
    global _missing_key_warned
    if not titles:
        return []
    if not api_key or not api_key.strip():
        if not _missing_key_warned:
            print("OpenAI API key missing — sentiment disabled.")
            _missing_key_warned = True
        return ["neutral"] * len(titles)
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles) if t and str(t) != "nan")
    if not numbered.strip():
        return ["neutral"] * len(titles)
    prompt = f'Classify each headline as exactly one word: positive, negative, or neutral. Reply with only those words, one per line, in the same order as the headlines.\n\n{numbered}'
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0,
                },
            )
        print("Sentiment API status:", resp.status_code)
        if resp.status_code != 200:
            logger.warning("OpenAI sentiment batch returned status %s", resp.status_code)
            return ["neutral"] * len(titles)
        out = resp.json()
        text = out["choices"][0]["message"]["content"]
        print("Sentiment API raw output:", text)
        return _parse_sentiment_response(text, len(titles))
    except Exception as e:
        print("Sentiment API error:", e)
        logger.exception("OpenAI sentiment batch failed: %s", e)
        return ["neutral"] * len(titles)


def get_sentiments_parallel(titles: list[str], api_key: Optional[str]) -> list[str]:
    """Get sentiments for many titles. Results are in same order as titles (batch start index mapping)."""
    if not titles:
        return []
    n = len(titles)
    results: list[Optional[str]] = [None] * n
    # Build (start_index, batch) so we write to the correct slice regardless of completion order
    batch_specs: list[tuple[int, list[str]]] = [
        (i, titles[i : i + BATCH_SIZE])
        for i in range(0, n, BATCH_SIZE)
    ]

    def _run_batch(spec: tuple[int, list[str]]) -> tuple[int, list[str]]:
        start_idx, batch = spec
        sentiments = get_sentiments_batch(batch, api_key)
        return (start_idx, sentiments)

    with ThreadPoolExecutor(max_workers=MAX_SENTIMENT_WORKERS) as executor:
        futures = {executor.submit(_run_batch, spec): spec for spec in batch_specs}
        for future in as_completed(futures):
            start_idx, sentiments = future.result()
            for j, s in enumerate(sentiments):
                if start_idx + j < n:
                    results[start_idx + j] = s
    return [r or "neutral" for r in results]


def get_sentiment(title: str, api_key: Optional[str]) -> str:
    """Classify headline sentiment: positive, negative, neutral."""
    if not api_key or not api_key.strip() or not title or (isinstance(title, float) and str(title) == "nan"):
        return "neutral"
    prompt = f'Classify this news headline sentiment as exactly one of: positive, negative, neutral. Reply with only that one word.\n\nHeadline: "{title}"'
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0,
                },
            )
        if resp.status_code != 200:
            return "neutral"
        out = resp.json()
        ans = out["choices"][0]["message"]["content"].strip().lower()
        return ans if ans in ("positive", "negative", "neutral") else "neutral"
    except Exception as e:
        logger.exception("OpenAI sentiment single failed: %s", e)
        return "neutral"


def get_summary(
    title: str,
    abstract: str,
    subtitle: Optional[str] = None,
    tone: str = "Informational",
    api_key: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> str:
    """Get AI summary (2-3 lines) with specified tone. Optional client for reuse in thread."""
    if not api_key or not api_key.strip():
        return abstract if abstract else title
    text_parts = [title, subtitle, abstract] if subtitle else [title, abstract]
    text = " ".join(str(p) for p in text_parts if p and str(p) != "nan").strip()
    if not text:
        return "No summary available."
    tone_instructions = {
        "Opinion": "Provide a brief opinionated 2-3 sentence summary.",
        "Analytical": "Provide a brief analytical 2-3 sentence summary that examines causes and implications.",
        "Informational": "Provide a brief neutral, informational 2-3 sentence summary.",
    }
    tone_instruction = tone_instructions.get(tone, tone_instructions["Informational"])
    prompt = f"{tone_instruction}\n\nText: {text}"
    try:
        if client is not None:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0.3,
                },
            )
        else:
            with httpx.Client(timeout=30.0) as c:
                resp = c.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": OPENAI_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 150,
                        "temperature": 0.3,
                    },
                )
        if resp.status_code != 200:
            logger.warning("OpenAI summary returned status %s", resp.status_code)
            return abstract if abstract else title
        out = resp.json()
        return out["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.exception("OpenAI summary failed: %s", e)
        return abstract if abstract else title


def get_summaries_parallel(
    items: list[tuple[str, str, Optional[str]]],
    tone: str,
    api_key: Optional[str],
) -> list[str]:
    """Get summaries in parallel; each worker reuses one httpx.Client. Max 3 workers."""
    if not items:
        return []
    if not api_key or not api_key.strip():
        return [t[1] or t[0] for t in items]

    def _worker(item_chunk: list[tuple[str, str, Optional[str]]]) -> list[str]:
        out = []
        with httpx.Client(timeout=30.0) as client:
            for title, abstract, subtitle in item_chunk:
                s = get_summary(title, abstract, subtitle, tone, api_key, client=client)
                out.append(s)
        return out

    # Split items into MAX_SUMMARY_WORKERS chunks so each worker gets one client
    n = len(items)
    chunk_size = max(1, (n + MAX_SUMMARY_WORKERS - 1) // MAX_SUMMARY_WORKERS)
    chunks = [items[i : i + chunk_size] for i in range(0, n, chunk_size)]
    with ThreadPoolExecutor(max_workers=MAX_SUMMARY_WORKERS) as executor:
        chunk_results = list(executor.map(_worker, chunks))
    result = []
    for r in chunk_results:
        result.extend(r)
    return result
