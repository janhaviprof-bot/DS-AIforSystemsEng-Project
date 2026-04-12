# News for People in Hurry

A Shiny for Python app that fetches NYT Top Stories, categorizes and scores news (breaking, trending, sentiment), and displays them with AI-generated summaries.

## Setup

### 1. Install Python packages

```bash
pip install -r requirements.txt
```

Or with uv:

```bash
uv pip install -r requirements.txt
```

### 2. API keys

Add your API keys to the **project root** `.env` file:

```
NYT_API_KEY=your_nytimes_api_key
OPENAI_API_KEY=your_openai_api_key
```

- **NYT API key**: Get one at [developer.nytimes.com](https://developer.nytimes.com/)
- **OpenAI API key**: Get one at [platform.openai.com](https://platform.openai.com/)

### 3. Run the app

From the project root or from `AppV1`:

```bash
cd AppV1
python app.py
```

The app opens in your default browser automatically.

The app loads `.env` from the project root (parent of AppV1).

## Documentation

- **Comprehensive architecture (diagrams, agents, tools, UI, caching, modules):** [`../docs/README-AppV1-Multi-Agent-Architecture.md`](../docs/README-AppV1-Multi-Agent-Architecture.md)
- **Agents (short prompts & tool note):** [`AGENTS.md`](AGENTS.md)
- **Doc bundle version:** [`../docs/VERSION.md`](../docs/VERSION.md)

## Performance and loading (recent behavior)

- **Progressive refresh:** After NYT data is fetched, the feed is published immediately with placeholder sentiment/impact so the homepage can render; sentiment and impact enrichment run in a **separate reactive cycle** so Shiny can flush the UI first.
- **Signal Studio preload:** After that first paint, the app arms the agent pipeline and bumps `agent_refresh_token` so **Signal Studio work starts in the background** without requiring a tab click. A second bump runs after deferred enrichment completes so results reflect real labels.
- **Two-phase agent pipeline:** The first pass builds section packets **without** LLM article summaries (headlines/abstracts only), shows **quick** section briefs and a **deterministic** Signal Studio snapshot, then a background effect runs full LLM briefs + `run_multi_agent_workflow` and upgrades the UI.
- **HTTP efficiency:** NYT fetches reuse one `httpx` client; sentiment and impact batching can share clients and run concurrently where applicable (see `modules/ai_services.py`, `modules/impact_classifier.py`).

## NYT API resilience

- If every section fails in one refresh (e.g. **HTTP 429** rate limits), `modules/data_fetch.py` can serve the **last successful merged feed** from an in-memory cache for a short TTL (~3 minutes) so the app does not go blank.

## Features

- **Categories**: ALL, business, sports, arts, technology, world, politics
- **Card order**: First 6 cards prioritize breaking (2) → trending (2) → latest (2); pagination continues with latest only
- **Time filter**: Show articles from the past 6–48 hours
- **Sentiment filter**: positive, negative, neutral (optional)
- **Summary tone**: Informational, Opinion, or Analytical

## Project structure

```
AppV1/
├── app.py           # Main Shiny app
├── config.py        # Load .env from root, API keys
├── buildplan.md     # Implementation notes (if present)
├── agents/          # Multi-agent workflow, LLM client, market data
├── ui/              # Layout, Signal Studio, marquee
├── modules/
│   ├── data_fetch.py      # NYT API
│   ├── categorization.py  # Breaking, trending, latest
│   ├── ai_services.py     # OpenAI sentiment & summary
│   └── news_cards.py      # Card UI
├── research_agent/  # Optional research brief modal
└── www/
    ├── styles.css
    └── placeholder.svg
```
