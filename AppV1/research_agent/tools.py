# research_agent/tools.py — Wikipedia, Yahoo Finance (used by the tool-calling agent)

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

# Wikimedia asks for a descriptive User-Agent: https://meta.wikimedia.org/wiki/User-Agent_policy
HTTP_HEADERS = {
    "User-Agent": "NewsForPeopleInHurry/1.0 (research-agent; +https://github.com/)",
}

WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def wikipedia_lookup(query: str, max_extract_chars: int = 1500) -> str:
    """Search English Wikipedia and return title + summary extract (truncated)."""
    q = (query or "").strip()
    if not q:
        return "Error: empty Wikipedia query."
    try:
        with httpx.Client(timeout=20.0, headers=HTTP_HEADERS) as client:
            r = client.get(
                WIKI_SEARCH,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": q,
                    "format": "json",
                    "srlimit": 3,
                },
            )
        if r.status_code != 200:
            return f"Wikipedia search failed (HTTP {r.status_code})."
        data = r.json()
        hits = (data.get("query") or {}).get("search") or []
        if not hits:
            return f"No Wikipedia results for: {q!r}"
        title = hits[0].get("title") or ""
        if not title:
            return "Wikipedia returned an empty title."

        enc = quote(title.replace(" ", "_"), safe="")
        summary_path = WIKI_SUMMARY.format(title=enc)
        with httpx.Client(timeout=20.0, headers=HTTP_HEADERS) as client:
            r2 = client.get(summary_path)
        if r2.status_code == 404:
            return f"Wikipedia page not found for title: {title!r}"
        if r2.status_code != 200:
            return f"Wikipedia summary failed (HTTP {r2.status_code})."
        body = r2.json()
        extract = (body.get("extract") or "").strip()
        if not extract:
            desc = (body.get("description") or "").strip()
            extract = desc or "(No extract available.)"
        if len(extract) > max_extract_chars:
            extract = extract[: max_extract_chars - 3] + "..."
        return f"Title: {title}\n\n{extract}"
    except Exception as e:
        logger.exception("wikipedia_lookup failed: %s", e)
        return f"Wikipedia error: {e!s}"


def _pick_info_fields(info: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "symbol",
        "shortName",
        "longName",
        "currency",
        "regularMarketPrice",
        "regularMarketPreviousClose",
        "regularMarketChangePercent",
        "marketCap",
        "trailingPE",
        "fiftyTwoWeekHigh",
        "fiftyTwoWeekLow",
    ]
    out: dict[str, Any] = {}
    for k in keys:
        v = info.get(k)
        if v is not None and v != "":
            out[str(k)] = v
    return out


def yahoo_finance_quote(ticker: str) -> str:
    """Return a compact Yahoo Finance snapshot for a ticker (e.g. AAPL, MSFT)."""
    sym = (ticker or "").strip().upper()
    if not sym:
        return "Error: empty ticker."
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        if not info or (info.get("regularMarketPrice") is None and not info.get("shortName")):
            return f"No Yahoo Finance data for ticker: {sym!r}"
        sub = _pick_info_fields(info)
        return "Yahoo Finance:\n" + json.dumps(sub, indent=2, default=str)
    except Exception as e:
        logger.exception("yahoo_finance_quote failed: %s", e)
        return f"Yahoo Finance error: {e!s}"


def dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    """Run a tool by OpenAI function name; return plain-text result for the model."""
    if name == "wikipedia_lookup":
        return wikipedia_lookup(
            str(arguments.get("query", "")),
            int(arguments.get("max_extract_chars") or 1500),
        )
    if name == "yahoo_finance_quote":
        return yahoo_finance_quote(str(arguments.get("ticker", "")))
    return f"Unknown tool: {name!r}"
