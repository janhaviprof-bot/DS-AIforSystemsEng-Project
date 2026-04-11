# Rubric self-assessment (comparison tables)

**Bundle:** Same release as [README-AppV1-Multi-Agent-Architecture.md](./README-AppV1-Multi-Agent-Architecture.md).  
**Scope:** AppV1 Shiny app (Signal Studio + Dive deeper). **`ollama_agents/`** is CLI-only and **not** imported by `app.py`.

---

## Table 1 — [25 pts] Agentic orchestration

| Requirement | Present? | Notes |
| :--- | :--- | :--- |
| 2–3 agents working together | **Yes (in live app)** | **Signal Studio** runs **three** coordinated OpenAI agents in series (cross-section → world mood → market validation), plus parallel **section brief** LLM calls. **`ollama_agents`**: 2-agent chain exists but is **CLI-only**, not wired to the Shiny UI. |
| Clear role + system prompt per agent | **Yes** | Each of Agents 1–3 has its own module and system prompt under `AppV1/agents/` (`cross_section_agent`, `world_sentiment_agent`, `market_validation_agent`). Section briefs use `section_brief_agent`. |
| Agents coordinate on workflow goals | **Yes (Signal Studio)** | `run_multi_agent_workflow()` passes Agent 1 output → Agent 2 → market snapshot → Agent 3. **Dive deeper** is a **separate** single **tool-calling** loop (`run_research_brief`), not the 3-agent chain. |
| Outputs integrated into app | **Yes** | **Global Insight** marquee, **per-tab section briefs**, and **Signal Studio** tab consume `agent_workflow_state` / `section_brief_state`. **Research brief modal** integrates tool-calling output for Dive deeper. |

---

## Table 2 — [25 pts] RAG or tool calling (at least one)

| Requirement | Present? | Notes |
| :--- | :--- | :--- |
| **Tool calling** (APIs / functions) | **Yes** | **Dive deeper:** OpenAI **function calling** with **Wikipedia** + **Yahoo Finance** tools (`research_agent/agent.py`, `dispatch_tool`). Signal Studio Agents 1–3 use chat completions only; **yfinance** runs in Python before Agent 3, not as LLM-invoked tools. |
| **RAG** (custom text / CSV / SQLite) | **No** | No embedding index or retrieval over a **your** static corpus. Context for Signal Studio is built from the **live article DataFrame** (not classic RAG). Live Wikipedia via tool is **not** RAG over local files. |

---

## Table 3 — Present vs not (quick checklist)

| Item | Status |
| :--- | :--- |
| Multi-agent (2–3) in **running** Shiny app | **Present** — Signal Studio: 3 named agents + brief batch. **Not in UI:** Ollama 2-agent pipeline (`ollama_agents/`) — CLI only. |
| Clear agent roles in the **product** | **Present** — Signal Studio agents are first-class in UI; prompts in code. |
| Coordination **agent ↔ agent** | **Present** — OpenAI pipeline Agent 1 → 2 → (market) → 3. **Separate:** Dive deeper = model ↔ **tools** (not multi-agent chain). |
| Tool-calling requirement | **Met** — Two tools on **Dive deeper** (research brief). |
| RAG option | **Not implemented** — acceptable if rubric allows **tool calling only**. |

---

## Summary sentence (for write-ups)

We implement **both** (1) **multi-agent orchestration** in the running app via **Signal Studio**—three sequential OpenAI agents with section briefs, driving the header marquee and dashboard—and (2) the **tool-calling** option via **Dive deeper** (OpenAI function calling with Wikipedia and Yahoo Finance). **`ollama_agents`** provides an additional two-agent Ollama demo **outside** the Shiny UI. **RAG** over a custom local corpus is not implemented; external context for Dive deeper uses **tools**, not retrieval from your own files/DB.

---

*Part of the AppV1 multi-agent documentation bundle; see [VERSION.md](./VERSION.md).*
