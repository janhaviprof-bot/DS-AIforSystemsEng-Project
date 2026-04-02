# Research agent

This package runs an **OpenAI tool-calling loop** that turns a single news story (title, abstract, section, URL) into a short **research brief**. The model may call:

- **`wikipedia_lookup`** — English Wikipedia search + summary extract (via the [MediaWiki](https://www.mediawiki.org/wiki/API:Main_page) and [REST summary](https://en.wikipedia.org/api/rest_v1/) APIs; a descriptive `User-Agent` is sent per Wikimedia policy).
- **`yahoo_finance_quote`** — Market snapshot for a ticker via the [`yfinance`](https://pypi.org/project/yfinance/) library (unofficial Yahoo Finance data).

There is **no** local database; tools fetch live data over the network. The chat model is **`gpt-4o-mini-2024-07-18`**, set as `OPENAI_MODEL` in `config.py` and used for all OpenAI Chat Completions in the app.

## Files

| File | Role |
|------|------|
| `tools.py` | Tool implementations and `dispatch_tool(name, arguments)` for the OpenAI function names. |
| `agent.py` | `OPENAI_TOOLS` JSON schemas, system prompt, `run_research_brief(...)`, and a small `__main__` demo. |
| `__init__.py` | Public exports: `run_research_brief`, `OPENAI_TOOLS`, `dispatch_tool`. |

## Configuration

- **`OPENAI_API_KEY`** — Required for `run_research_brief`. Loaded the same way as the rest of AppV1 (`config.py` / `.env`). If the key is missing, the app shows an error in the research modal instead of calling OpenAI.

## CLI smoke test (optional)

From the `AppV1` directory (with `.env` containing `OPENAI_API_KEY`):

```bash
python -m research_agent.agent
```

## Integration with the Shiny app

The research agent is **wired into the main dashboard** as follows.

### Sidebar UI

- **File:** `ui/layout.py`
- **Section:** Card titled **“Research brief (AI)”**, with:
  - `input_select("research_article_url", …)` — choices list the articles on the **current category tab** and **current page** (same six-card window as the grid).
  - `input_action_button("research_generate", …)` — runs the agent for the selected URL.

### Server logic and modal

- **File:** `app.py`
- **Import:** `from research_agent import run_research_brief`
- **Reactive state:** `research_brief_state` — `phase` is one of `idle`, `loading`, `done`, `error`; `text` holds the brief or error message.
- **Syncing the dropdown:** `_research_select_sync` calls `ui.update_select` when the active tab, filters, pagination, or feed changes (`research_article_choices()` uses `current_cards_for` aligned with `input.category_tabs()`).
- **Tab values:** Each `ui.nav_panel` sets a explicit `value=` (`ALL`, `business`, `arts`, etc.) and `navset_tab(selected=…)` uses **`ALL`** so the selected tab string matches the keys used by `current_cards_for`.
- **Run brief:** `_research_generate` (async) shows a **modal** (`ui.modal_show` + `_research_modal()`) and runs `run_research_brief` in **`asyncio.to_thread`** so the session is not blocked while OpenAI and tools run.
- **Modal body:** `@render.ui def research_modal_body` — reads `research_brief_state()` so the dialog updates from loading → result or error.

### Styling

- **File:** `www/styles.css` — classes `.research-brief-pre`, `.research-modal-inner`, `.research-loading`, `.research-error`.

## User flow

1. Load articles (**Refresh News**).
2. Open the category tab and page that contains the story you care about.
3. In the sidebar, choose the story in **Story on current tab / page**.
4. Click **Generate research brief** and wait for the modal (Wikipedia / Yahoo calls may add a few seconds).

## Dependencies

Listed in `AppV1/requirements.txt` (notably `yfinance` alongside the existing stack). Wikipedia and Yahoo tool calls do not use extra API keys beyond OpenAI.
