# impact_classifier.py - LLM-based impact classification (positive/negative/neutral) with TTL cache
# Separate from ai_services; impact = societal benefit/harm, not tone.

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
MAX_IMPACT_WORKERS = 3
TTL_SECONDS = 30 * 60  # 30 minutes

# url -> {"label": str, "timestamp": datetime (UTC)}
impact_cache: dict = {}
_missing_key_error_logged = False  # Log ERROR once when API key missing

IMPACT_PROMPT = """Classify each news item by IMPACT (societal/economic/human impact), not tone or style.

Definitions:
- Positive: societal benefit, progress, economic growth, scientific advancement, job creation, peace, major wins.
- Negative: harm, crisis, war, layoffs, inflation risk, environmental damage, health threats, corruption.
- Neutral: purely informational reporting without clear beneficial or harmful impact.

Reply with exactly one word per item: positive, negative, or neutral. One word per line, in the same order as the items."""


def _parse_impact_response(text: str, n_expected: int) -> list[str]:
    """Parse batch impact response. Handles numbered lines, commas, newlines."""
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


def _is_expired(entry: dict) -> bool:
    if not entry or "timestamp" not in entry:
        return True
    try:
        ts = entry["timestamp"]
        if hasattr(ts, "timestamp"):
            age = (datetime.now(timezone.utc).timestamp() - ts.timestamp())
        else:
            age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > TTL_SECONDS
    except Exception:
        return True


def get_impact_batch(
    items: list[tuple[str, str, Optional[str], str]], api_key: Optional[str]
) -> list[str]:
    """
    Batch classify up to 10 items per request.
    items: list of (url, title, subtitle, abstract). subtitle may be None.
    Returns list of labels in same order. Updates impact_cache for each url.
    """
    global _missing_key_error_logged
    if not items:
        return []
    if not api_key or not str(api_key).strip():
        if not _missing_key_error_logged:
            logger.error(
                "Impact classifier: OPENAI_API_KEY is missing or empty. All impact labels will be neutral until key is set. Check .env and config loading."
            )
            _missing_key_error_logged = True
        logger.warning(
            "Impact classifier: FALLBACK returning neutral for batch of %s items (API key missing)", len(items)
        )
        now = datetime.now(timezone.utc)
        for url, _, _, _ in items:
            if url:
                impact_cache[url] = {"label": "neutral", "timestamp": now}
        return ["neutral"] * len(items)

    lines = []
    for url, title, subtitle, abstract in items:
        title_s = str(title).strip() if title is not None and not (isinstance(title, float) and pd.isna(title)) else ""
        sub_s = ""
        if subtitle is not None and not (isinstance(subtitle, float) and pd.isna(subtitle)):
            sub_s = str(subtitle).strip()
        abs_s = str(abstract).strip() if abstract is not None and not (isinstance(abstract, float) and pd.isna(abstract)) else ""
        parts = [f"Title: {title_s}"]
        if sub_s:
            parts.append(f"Subtitle: {sub_s}")
        parts.append(f"Abstract: {abs_s}")
        lines.append("\n".join(parts))

    numbered = "\n\n---\n\n".join(f"{i+1}.\n{t}" for i, t in enumerate(lines))
    prompt = f"{IMPACT_PROMPT}\n\n{numbered}"

    model = "gpt-3.5-turbo"
    n_items = len(items)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0,
                },
            )
        status = resp.status_code
        # Explicit API call logging
        if status != 200:
            body = resp.text[:300] if resp.text else "(empty)"
            logger.error(
                "Impact classifier API failed: status_code=%s response_preview=%s",
                status,
                body,
            )
            logger.warning(
                "Impact classifier: FALLBACK returning neutral for %s items (API returned %s)", n_items, status
            )
            now = datetime.now(timezone.utc)
            for url, _, _, _ in items:
                if url:
                    impact_cache[url] = {"label": "neutral", "timestamp": now}
            return ["neutral"] * len(items)
        out = resp.json()
        text = out["choices"][0]["message"]["content"]
        labels = _parse_impact_response(text, n_items)
        parse_ok = len(labels) == n_items and all(lb in ("positive", "negative", "neutral") for lb in labels)
        dist = pd.Series(labels).value_counts().to_dict()
        logger.info(
            "Impact batch: API status_code=200 model=%s n_items=%s parsing_ok=%s label_distribution=%s",
            model,
            n_items,
            parse_ok,
            dist,
        )
        if not parse_ok:
            logger.warning(
                "Impact batch: parsing produced %s labels for %s items; filling missing with neutral",
                len(labels),
                n_items,
            )
        now = datetime.now(timezone.utc)
        for i, (url, _, _, _) in enumerate(items):
            if url:
                impact_cache[url] = {"label": labels[i] if i < len(labels) else "neutral", "timestamp": now}
        return labels
    except Exception as e:
        logger.exception("Impact classifier batch failed: %s", e)
        logger.warning(
            "Impact classifier: FALLBACK returning neutral for %s items (exception)", n_items
        )
        now = datetime.now(timezone.utc)
        for url, _, _, _ in items:
            if url:
                impact_cache[url] = {"label": "neutral", "timestamp": now}
        return ["neutral"] * len(items)


def get_impact_parallel(
    items: list[tuple[str, str, Optional[str], str]], api_key: Optional[str]
) -> list[str]:
    """
    Parallelize batches (max 3 workers). Preserve ordering.
    items: list of (url, title, subtitle, abstract).
    """
    if not items:
        return []
    n = len(items)
    results: list[Optional[str]] = [None] * n
    batch_specs: list[tuple[int, list]] = [
        (i, items[i : i + BATCH_SIZE])
        for i in range(0, n, BATCH_SIZE)
    ]

    def _run_batch(spec: tuple[int, list]) -> tuple[int, list[str]]:
        start_idx, batch = spec
        labels = get_impact_batch(batch, api_key)
        return (start_idx, labels)

    with ThreadPoolExecutor(max_workers=MAX_IMPACT_WORKERS) as executor:
        futures = {executor.submit(_run_batch, spec): spec for spec in batch_specs}
        for future in as_completed(futures):
            start_idx, labels = future.result()
            for j, lab in enumerate(labels):
                if start_idx + j < n:
                    results[start_idx + j] = lab
    return [r or "neutral" for r in results]


def get_impacts_for_articles(arts: pd.DataFrame, api_key: Optional[str]) -> list[str]:
    """
    For each article row: use cache if valid, else classify.
    Only calls LLM for URLs not in cache or with expired TTL.
    Returns list of impact labels in same order as arts.
    """
    if arts is None or arts.empty:
        return []
    urls = arts["url"].tolist()
    title_col = arts.get("title", pd.Series([""] * len(arts)))
    subtitle_col = arts.get("subtitle", pd.Series([None] * len(arts)))
    abstract_col = arts.get("abstract", pd.Series([""] * len(arts)))

    need_items: list[tuple[str, str, Optional[str], str]] = []
    need_indices: list[int] = []
    now = datetime.now(timezone.utc)

    for i, url in enumerate(urls):
        if not url or (isinstance(url, float) and pd.isna(url)):
            need_items.append(("", str(title_col.iloc[i]) if i < len(title_col) else "", None, str(abstract_col.iloc[i]) if i < len(abstract_col) else ""))
            need_indices.append(i)
            continue
        entry = impact_cache.get(url)
        if entry is None or _is_expired(entry):
            title = title_col.iloc[i] if i < len(title_col) else ""
            sub = subtitle_col.iloc[i] if i < len(subtitle_col) else None
            abs_val = abstract_col.iloc[i] if i < len(abstract_col) else ""
            need_items.append((str(url), str(title) if title is not None else "", sub if sub is not None else None, str(abs_val) if abs_val is not None else ""))
            need_indices.append(i)

    n_from_cache = len(urls) - len(need_items)
    if need_items:
        logger.info(
            "Impact classifier: classification triggered for %s articles (cache miss or TTL expired); %s from cache",
            len(need_items),
            n_from_cache,
        )
        if not api_key or not str(api_key).strip():
            logger.warning("Impact classifier: get_impacts_for_articles called with empty API key; LLM will not be used")
        get_impact_parallel(need_items, api_key)  # updates impact_cache inside get_impact_batch
    else:
        logger.info("Impact classifier: all %s articles served from cache (no LLM call)", len(urls))

    out = []
    for i, url in enumerate(urls):
        if not url or (isinstance(url, float) and pd.isna(url)):
            out.append("neutral")
            continue
        entry = impact_cache.get(url)
        out.append(entry["label"] if entry else "neutral")
    return out
