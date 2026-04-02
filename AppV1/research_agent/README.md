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

### Card UI

- **File:** `modules/news_cards.py` — `news_card_ui(..., dive_input_id=…)` renders **Dive Deeper** (`ui.input_action_link`) on the **same row** as **Read on NYT** (flex footer: left / right).
- **File:** `app.py` — `make_cards_ui(cat)` passes `dive_input_id=f"dive_{cat}_{i}"` so each slot has a stable id (e.g. `dive_business_2`).

### Server logic and modal

- **File:** `app.py`
- **Import:** `from research_agent import run_research_brief`
- **Reactive state:** `research_brief_state` — `phase` is one of `idle`, `loading`, `done`, `error`; `text` holds the brief or error message.
- **Handlers:** `_bind_dive_deeper_handlers()` registers effects for `dive_{category}_{0..5}`; each click resolves the article URL from `current_cards_for(category)` and calls **`_run_research_brief_for_url`**.
- **Run brief:** `_run_research_brief_for_url` shows the **modal** (`ui.modal_show` + `_research_modal()`) and runs `run_research_brief` in **`asyncio.to_thread`** so the session is not blocked while OpenAI and tools run.
- **Modal body:** `@render.ui def research_modal_body` — reads `research_brief_state()` so the dialog updates from loading → result or error.
- **Tabs:** `nav_panel` `value=` strings (`ALL`, `business`, …) match the `cat` passed into `make_cards_ui`.

### Styling

- **File:** `www/styles.css` — `.card-footer-row`, `.card-footer-left`, `.card-footer-right`, and link/button overrides for **Dive Deeper**; modal classes `.research-brief-pre`, `.research-modal-inner`, `.research-loading`, `.research-error`.

## User flow

1. Load articles (**Refresh News**).
2. On any story card, click **Dive Deeper** (left side of the footer row); **Read on NYT** stays on the right.
3. Wait for the modal (Wikipedia / Yahoo calls may add a few seconds).

## Dependencies

Listed in `AppV1/requirements.txt` (notably `yfinance` alongside the existing stack). Wikipedia and Yahoo tool calls do not use extra API keys beyond OpenAI.
