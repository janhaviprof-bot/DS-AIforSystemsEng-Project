# research_agent/agent.py — OpenAI tool-calling loop (Wikipedia, Yahoo Finance)

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from config import OPENAI_MODEL

from .tools import dispatch_tool

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "wikipedia_lookup",
            "description": (
                "Look up a concise English Wikipedia summary for a person, place, company, or concept. "
                "Use a short search query (not a full sentence)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'Federal Reserve' or 'OpenAI'.",
                    },
                    "max_extract_chars": {
                        "type": "integer",
                        "description": "Max characters of the summary extract (default 1500).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "yahoo_finance_quote",
            "description": (
                "Fetch current Yahoo Finance snapshot for a stock ticker. "
                "Use only when the article is clearly about markets or a specific public company (e.g. AAPL, MSFT)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "US ticker symbol, e.g. AAPL, GOOGL, JPM.",
                    },
                },
                "required": ["ticker"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a careful research assistant for a news reader app.
Given one NYT-style article (title, abstract, section), you may call tools to gather context:
Wikipedia for background, Yahoo Finance only when the story is clearly about a stock/market ticker.

Rules:
- Call tools sparingly (typically 1–4 calls total) and only when they add value.
- Prefer short Wikipedia queries.
- After tools (or if none are needed), write a concise research brief: 3–6 short paragraphs or bullet sections.
- Avoid using # and * symbols in the brief.
- Attribute sources in plain language (e.g. 'Wikipedia notes…', 'Yahoo Finance shows…').
- Do not invent tool results; only use what tools return.
- If a tool errors, say so briefly and continue."""


def _parse_arguments(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON tool arguments: %s", raw[:200])
        return {}


def run_research_brief(
    *,
    title: str,
    abstract: str = "",
    subtitle: str = "",
    section: str = "",
    article_url: str = "",
    api_key: Optional[str] = None,
    max_rounds: int = 8,
) -> str:
    """
    Run the tool-calling agent and return a markdown-flavored plain-text brief.
    Uses ``OPENAI_MODEL`` from ``config`` (same as sentiment, summaries, and impact).
    """
    if not api_key or not str(api_key).strip():
        return "OpenAI API key is required. Set OPENAI_API_KEY in the environment."

    user_lines = [
        f"Title: {title}",
        f"Section: {section}" if section else "",
        f"URL: {article_url}" if article_url else "",
    ]
    if subtitle:
        user_lines.append(f"Subtitle: {subtitle}")
    if abstract:
        user_lines.append(f"Abstract: {abstract}")
    user_content = "\n".join(line for line in user_lines if line)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    with httpx.Client(timeout=90.0) as client:
        for _ in range(max_rounds):
            resp = client.post(
                CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": messages,
                    "tools": OPENAI_TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.3,
                },
            )
            if resp.status_code != 200:
                logger.warning("OpenAI chat failed: %s %s", resp.status_code, resp.text[:500])
                return f"OpenAI request failed (HTTP {resp.status_code})."

            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason")

            tool_calls = message.get("tool_calls")
            if tool_calls:
                messages.append(message)
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    args_raw = fn.get("arguments") or "{}"
                    parsed = _parse_arguments(args_raw)
                    result = dispatch_tool(name, parsed)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        }
                    )
                continue

            content = (message.get("content") or "").strip()
            if content:
                return content
            if finish_reason in ("length", "content_filter"):
                return f"Research brief incomplete (finish_reason={finish_reason!r})."
            return "Empty response from the model."

    return "Research brief stopped: maximum tool rounds exceeded."


if __name__ == "__main__":
    import os
    from pathlib import Path

    from dotenv import load_dotenv

    # Allow running from repo root or AppV1
    for p in Path(__file__).resolve().parents:
        env = p / ".env"
        if env.is_file():
            load_dotenv(env)
            break
    load_dotenv(override=False)

    key = os.getenv("OPENAI_API_KEY")
    out = run_research_brief(
        title="Markets react to central bank guidance",
        abstract="Stocks moved sharply after officials signaled a slower path for rate cuts.",
        section="business",
        api_key=key,
    )
    print(out)
