# Ollama two-agent pipeline (assignment-style)

Uses **local Ollama** only (not OpenAI).

## Task 1 — Custom tool

**File: `tools.py`**

| Deliverable | What we use |
|-------------|-------------|
| **Custom function** | `wikipedia_summary(query)` — calls Wikipedia’s search + page summary API (real HTTP fetch, useful for the news app). |
| **Tool metadata** | `TOOL_METADATA` — JSON-schema style `name`, `description`, and `parameters` for Ollama’s `/api/chat` `tools` array. |
| **Dispatcher** | `dispatch_tool(name, arguments)` — runs the function by name with the parsed args the model sent. |

## Task 2 — Two-agent workflow

**File: `functions.py`**

| Agent | Role |
|-------|------|
| **Agent 1** | **Uses tools** — default prompt instructs the model to call `wikipedia_summary` for key topics in the user’s snippet, then summarize what was fetched. Implemented via `run_agent_with_tools`. |
| **Agent 2** | **No tools** — takes Agent 1’s output + original user text and writes a **report / analysis** (`chat_simple`). |

**`agent_run(agent1, agent2, user_input, ollama_base=...)`** chains them and returns **`AgentPipelineResult`** (`agent1_output`, `agent2_output`). **`main.py`** prints both.

## Run

```bash
cd AppV1
python -m ollama_agents.main
```

Needs Ollama + a tool-capable model (e.g. `ollama pull llama3.2`).

Env: `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_DEMO_INPUT`.

## Wikipedia

MediaWiki + REST APIs; sends a descriptive `User-Agent`.
