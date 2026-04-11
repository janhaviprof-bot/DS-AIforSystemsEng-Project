import json
import logging
from typing import Any, Optional

import httpx

from config import OPENAI_MODEL

logger = logging.getLogger(__name__)
_shared_client: httpx.Client | None = None


def _client() -> httpx.Client:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client(timeout=45.0)
    return _shared_client


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def call_text_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    api_key: Optional[str],
    max_tokens: int = 250,
    temperature: float = 0.2,
) -> str | None:
    if not api_key or not str(api_key).strip():
        return None
    try:
        resp = _client().post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        if resp.status_code != 200:
            logger.warning("LLM text call returned status %s", resp.status_code)
            return None
        payload = resp.json()
        return payload["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("LLM text call failed: %s", exc)
        return None


def call_json_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    api_key: Optional[str],
    max_tokens: int = 700,
    temperature: float = 0.2,
) -> dict[str, Any] | None:
    if not api_key or not str(api_key).strip():
        return None
    try:
        resp = _client().post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
        )
        if resp.status_code != 200:
            logger.warning("LLM JSON call returned status %s", resp.status_code)
            return None
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"]
        return _extract_json_object(content)
    except Exception as exc:
        logger.warning("LLM JSON call failed: %s", exc)
        return None
