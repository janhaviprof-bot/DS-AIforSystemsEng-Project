# research_agent — tool-backed research briefs (Wikipedia, Yahoo Finance).

from __future__ import annotations

from .agent import OPENAI_TOOLS, run_research_brief
from .tools import dispatch_tool

__all__ = [
    "OPENAI_TOOLS",
    "dispatch_tool",
    "run_research_brief",
]
