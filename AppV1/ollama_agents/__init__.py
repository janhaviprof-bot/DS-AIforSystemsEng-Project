# ollama_agents — Agent 1 (context gaps) → Agent 2 (Wikipedia tool-calling) via Ollama.

from __future__ import annotations

from .functions import (
    AgentPipelineResult,
    AgentSpec,
    agent_run,
    chat_simple,
    default_agent1,
    default_agent2,
    run_agent_with_tools,
)
from .tools import TOOL_METADATA, dispatch_tool, wikipedia_summary

__all__ = [
    "AgentPipelineResult",
    "AgentSpec",
    "TOOL_METADATA",
    "agent_run",
    "chat_simple",
    "default_agent1",
    "default_agent2",
    "dispatch_tool",
    "run_agent_with_tools",
    "wikipedia_summary",
]
