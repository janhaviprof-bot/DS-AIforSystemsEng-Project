# Multi-agent LLM modules

Each agent module defines a single `AGENT_SYSTEM_PROMPT` (role instructions) and one main entry function used by `agents/workflow.py`.

| Agent | File | System prompt (summary) |
|-------|------|-------------------------|
| **Agent 1** — cross-section | [`agents/cross_section_agent.py`](agents/cross_section_agent.py) | Compare section briefs; find cross-section links, triggers, propagation; return compact JSON. |
| **Agent 2** — world sentiment | [`agents/world_sentiment_agent.py`](agents/world_sentiment_agent.py) | From Agent 1 plus sentiment counts, judge world mood, score, market stance; short paragraph + bullet reasoning; compact JSON. |
| **Agent 3** — market validation | [`agents/market_validation_agent.py`](agents/market_validation_agent.py) | Compare Agent 2 narrative to live market tape; align/diverge/truth; compact JSON. Uses OpenAI tool `get_market_snapshot` when the API supports it, then falls back to JSON mode with a prefetched snapshot. |

## Workflow snapshot vs Agent 3 tool data

`workflow.py` still calls `fetch_market_snapshot()` with no arguments and passes that dict into Agent 3 for **fallback** and includes it in the workflow result for the UI (“Market pulse”). When Agent 3 uses the tool, it may fetch a **symbol-specific** snapshot that can differ slightly from that default full-universe snapshot. That is expected and keeps caching and UI behavior unchanged.
