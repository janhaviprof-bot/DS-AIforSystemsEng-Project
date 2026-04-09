# ollama_agents/tools.py
#
# Task 1 — Custom tool
#   - Implementation: wikipedia_summary() (HTTP calls to Wikipedia APIs — useful for news context).
#   - Metadata: TOOL_METADATA (JSON Schema for Ollama / OpenAI-style tool calling).

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "NewsInHurryOllamaAgents/1.0 (educational; +https://github.com/)",
}

WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

# Task 1 — tool metadata: name, description, parameters (required for the model to call the function)
TOOL_METADATA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "wikipedia_summary",
        "description": (
            "Look up a short English Wikipedia summary for a person, company, place, or concept. "
            "Pass a tight search phrase (e.g. 'Federal Reserve', 'OPEC'), not a full sentence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Wikipedia search query.",
                },
            },
            "required": ["query"],
        },
    },
}


def wikipedia_summary(query: str, max_chars: int = 1200) -> str:
    """Fetch top Wikipedia hit + REST extract; return plain text for the model."""
    q = (query or "").strip()
    if not q:
        return "Error: empty query."
    try:
        with httpx.Client(timeout=20.0, headers=HTTP_HEADERS) as client:
            r = client.get(
                WIKI_SEARCH,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": q,
                    "format": "json",
                    "srlimit": 1,
                },
            )
        if r.status_code != 200:
            return f"Wikipedia search failed (HTTP {r.status_code})."
        hits = (r.json().get("query") or {}).get("search") or []
        if not hits:
            return f"No Wikipedia results for: {q!r}"
        title = hits[0].get("title") or ""
        if not title:
            return "Wikipedia returned an empty title."
        enc = quote(title.replace(" ", "_"), safe="")
        summary_path = WIKI_SUMMARY.format(title=enc)
        with httpx.Client(timeout=20.0, headers=HTTP_HEADERS) as client:
            r2 = client.get(summary_path)
        if r2.status_code != 200:
            return f"Wikipedia summary failed (HTTP {r2.status_code})."
        body = r2.json()
        extract = (body.get("extract") or "").strip()
        if not extract:
            extract = (body.get("description") or "").strip() or "(No extract.)"
        if len(extract) > max_chars:
            extract = extract[: max_chars - 3] + "..."
        return f"Title: {title}\n\n{extract}"
    except Exception as e:
        logger.exception("wikipedia_summary: %s", e)
        return f"Wikipedia error: {e!s}"


def dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "wikipedia_summary":
        return wikipedia_summary(str(arguments.get("query", "")))
    return json.dumps({"error": f"unknown_tool: {name}"})
