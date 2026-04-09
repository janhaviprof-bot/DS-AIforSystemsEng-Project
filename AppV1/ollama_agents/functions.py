# ollama_agents/functions.py
#
# Task 2 — Two-agent workflow (see agent_run):
#   Agent 1: uses the custom tool (Wikipedia) to fetch / ground context.
#   Agent 2: no tools — report / analysis from Agent 1 output + original input.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .tools import TOOL_METADATA, dispatch_tool

logger = logging.getLogger(__name__)

# Tool list passed to Agent 1 (Task 2)
CUSTOM_TOOLS: list[dict[str, Any]] = [TOOL_METADATA]


@dataclass
class AgentSpec:
    system_prompt: str
    tools: Optional[list[dict[str, Any]]] = None
    model: str = "llama3.2"


@dataclass
class AgentPipelineResult:
    """Output from :func:`agent_run` — Agent 1 (text after using tools) and Agent 2 (final report)."""

    agent1_output: str
    agent2_output: str

    @property
    def final(self) -> str:
        """Same as ``agent2_output`` (convenience if you only need the last step)."""
        return self.agent2_output


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse tool arguments as JSON: %s", raw[:120])
            return {}
    return {}


def _tool_name_from_call(tc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    fn = tc.get("function") if isinstance(tc, dict) else None
    if not isinstance(fn, dict):
        return "", {}
    name = str(fn.get("name", "") or "")
    args = _parse_tool_arguments(fn.get("arguments"))
    return name, args


def run_agent_with_tools(
    *,
    model: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict[str, Any]],
    base_url: str,
    max_rounds: int = 6,
) -> tuple[str, list[dict[str, Any]]]:
    """One agent with tools: Ollama chat loop until the model returns text (no tool_calls)."""
    url = base_url.rstrip("/") + "/api/chat"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    with httpx.Client(timeout=180.0) as client:
        for round_i in range(max_rounds):
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": False,
            }
            if tools:
                payload["tools"] = tools
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Ollama chat HTTP %s: %s", resp.status_code, resp.text[:400])
                return (
                    f"[Ollama error HTTP {resp.status_code}] {resp.text[:500]}",
                    messages,
                )
            data = resp.json()
            msg = data.get("message")
            if not isinstance(msg, dict):
                return ("[Malformed Ollama response: no message]", messages)
            messages.append(msg)
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                content = msg.get("content")
                text = (content or "").strip() if isinstance(content, str) else ""
                return text, messages

            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                name, args = _tool_name_from_call(tc)
                if not name:
                    continue
                result = dispatch_tool(name, args)
                messages.append({"role": "tool", "tool_name": name, "content": result})
            logger.debug("Ollama tool round %s", round_i + 1)

    return ("[Stopped: max tool rounds]", messages)


def chat_simple(
    *,
    model: str,
    system_prompt: str,
    user_message: str,
    base_url: str,
) -> str:
    url = base_url.rstrip("/") + "/api/chat"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(
            url,
            json={"model": model, "messages": messages, "stream": False},
        )
        if resp.status_code != 200:
            return f"[Ollama error HTTP {resp.status_code}] {resp.text[:500]}"
        data = resp.json()
        msg = data.get("message") or {}
        c = msg.get("content")
        return (c.strip() if isinstance(c, str) else "") or "[Empty response]"


def agent_run(
    *,
    agent1: AgentSpec,
    agent2: AgentSpec,
    user_input: str,
    ollama_base: str = "http://127.0.0.1:11434",
) -> AgentPipelineResult:
    """
    Chain two agents (Task 2). Returns both outputs (see :class:`AgentPipelineResult`).

    1. **Agent 1** — Uses **custom tools** (e.g. ``wikipedia_summary``) to fetch or process
       data from the user’s news snippet.

    2. **Agent 2** — **No tools.** Takes Agent 1’s output plus the original user input and
       produces a report or analysis.
    """
    if agent1.tools:
        gaps_text, _ = run_agent_with_tools(
            model=agent1.model,
            system_prompt=agent1.system_prompt,
            user_message=user_input,
            tools=agent1.tools,
            base_url=ollama_base,
        )
    else:
        gaps_text = chat_simple(
            model=agent1.model,
            system_prompt=agent1.system_prompt,
            user_message=user_input,
            base_url=ollama_base,
        )

    agent2_message = (
        "--- Agent 1 output (includes commentary after tool calls) ---\n"
        f"{gaps_text}\n\n"
        "--- Original user input ---\n"
        f"{user_input}\n"
    )

    tools2 = agent2.tools or []
    if not tools2:
        text2 = chat_simple(
            model=agent2.model,
            system_prompt=agent2.system_prompt,
            user_message=agent2_message,
            base_url=ollama_base,
        )
    else:
        text2, _ = run_agent_with_tools(
            model=agent2.model,
            system_prompt=agent2.system_prompt,
            user_message=agent2_message,
            tools=tools2,
            base_url=ollama_base,
        )
    return AgentPipelineResult(agent1_output=gaps_text, agent2_output=text2)


def default_agent1(model: str) -> AgentSpec:
    return AgentSpec(
        model=model,
        tools=CUSTOM_TOOLS,
        system_prompt=(
            "You are Agent 1 — data gathering for a news reader app. "
            "You have ONE tool: wikipedia_summary(query). Read the user's headline and lede (or short paragraph). "
            "Identify 1–3 entities or topics where factual background would help (e.g. institution, policy name, "
            "foreign leader). For each important gap, call wikipedia_summary with a short query (2–6 words). "
            "Do not call the tool more than 3 times. After tool results return, write 2–5 sentences summarizing "
            "what Wikipedia added and how it relates to the story. Do not invent tool output."
        ),
    )


def default_agent2(model: str) -> AgentSpec:
    return AgentSpec(
        model=model,
        tools=None,
        system_prompt=(
            "You are Agent 2 — analyst and editor. You have NO tools. "
            "Using ONLY the 'Agent 1 output' section (which may include Wikipedia summaries) and the "
            "'Original user input' section, write a concise report for a busy reader:\n"
            "(1) One-line thesis: what the story is about.\n"
            "(2) Short analysis: why it matters, key players or mechanisms mentioned.\n"
            "(3) Background: integrate Wikipedia facts Agent 1 retrieved (say 'According to summaries…').\n"
            "(4) Optional: one sentence on limitations (what we still do not know).\n"
            "Stay under 250 words. Do not claim facts that are not in the provided text."
        ),
    )
