# AppV1 Backend Runtime Flow (What Exactly Happens)

This document explains the backend runtime behavior of `AppV1` in the order it actually executes.

## 1) App startup

1. `app.py` imports `config.py`.
2. `config.py` loads `.env` from:
   - `python-dotenv` search from current working directory,
   - parent directories from `AppV1` up to repo root,
   - then a final default `load_dotenv`.
3. It reads:
   - `NYT_API_KEY`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL` (`gpt-4o-mini-2024-07-18`)
4. Shiny app UI is created, then server state/caches are initialized.
5. On first server run, `_log_openai_key_once()` logs whether OpenAI key exists (length only, never value).

## 2) Core backend state and caches

Inside `server(...)`, backend state includes:

- `enriched_articles_state`: main DataFrame used by all tabs.
- `section_brief_state`: per-section brief text.
- `agent_workflow_state`: Signal Studio + marquee payload/status.
- `page_state`: pagination per tab.
- `last_refresh`, `is_loading`, `initial_load_done`.

In-memory caches:

- `sentiment_cache`: `url -> sentiment`
- `summary_cache`: `url|tone -> summary`
- `section_packet_cache`: hash key -> section packets
- `agent_pipeline_cache`: hash key -> full agent outputs
- NYT cache in `modules/data_fetch.py` (TTL 180s)
- Market snapshot cache in `agents/market_data.py` (TTL 10 min, full-universe snapshot only)

## 3) Initial load and refresh trigger

Two paths call the same refresh logic (`_run_refresh()`):

- Initial page load (`_initial_load` effect, runs once).
- User pressing the Refresh button (`input.refresh`).

Refresh begins by clearing the 4 app caches (`sentiment`, `summary`, `section packets`, `agent pipeline`), toggling loading state, and showing loading overlay.

## 4) Refresh phase 1: Fetch and publish quickly

`_run_refresh()` phase 1 does:

1. Validate `NYT_API_KEY`; if missing, store empty DataFrame and stop.
2. Fetch NYT top stories in parallel across configured sections via `fetch_nyt_articles(...)`.
3. In `fetch_nyt_articles(...)`:
   - each section uses `fetch_nyt_section(...)` over `httpx`,
   - successful section DataFrames are concatenated,
   - deduplicate by `url`,
   - attach `n_sections` metadata,
   - if all sections fail and recent cache exists (<=180s), return cached DataFrame.
4. Normalize `published_date` to UTC datetimes.
5. Apply article shaping pipeline:
   - `add_breaking_tag(...)`
   - `compute_trending_score(...)`
   - `sort_latest(...)`
6. Initialize placeholder columns:
   - `sentiment = neutral`
   - `impact_label = neutral`
7. Publish this DataFrame immediately to `enriched_articles_state` so feed renders fast.
8. Arm agent pipeline token for first run and schedule deferred enrichment (`_pending_enrich`).

Result: users see cards first, then AI enrichment updates afterward.

## 5) Refresh phase 2: Deferred AI enrichment

`_run_deferred_enrichment()` runs in the next reactive cycle:

1. Calls `_scoped_enrich_articles(arts, hours)` in a thread.
2. `_scoped_enrich_articles(...)`:
   - restricts work to URLs inside active time window (`filter_by_time`),
   - runs sentiment + impact classification concurrently (ThreadPoolExecutor with 2 workers),
   - sentiment uses `get_sentiments_parallel(...)` in batches,
   - impact uses `get_impacts_for_articles(...)`,
   - writes results back into article DataFrame.
3. Stores enriched DataFrame to `enriched_articles_state`.
4. Increments `agent_refresh_token` so multi-agent pipeline runs with latest data.

If user widens time range later, `_enrich_widen_time_window()` fills missing sentiment/impact for newly visible URLs only.

## 6) Runtime filters and card selection

Every render cycle uses `enriched_articles_state`:

1. `time_filtered_articles()`: applies `filter_by_time(...)`.
2. `filtered_articles()`: applies optional sentiment filter on top.
3. `category_articles_map()`: split into `ALL/business/arts/technology/world/politics`.
4. `current_cards_map()`: select 6-card page per category:
   - page 1 uses `select_first_six(...)` (breaking/trending/latest mix),
   - later pages use `select_next_six(...)` with used URL tracking.

## 7) Agent pipeline trigger and quick-first strategy

`_run_agent_pipeline()` starts when `agent_refresh_token` changes and pipeline is armed.

### Step A: Build section packets

`_build_agent_section_packets(include_summaries=False)` first:

- takes first 6 cards per workflow section,
- builds packet with headlines, URLs, sentiment counts, impact counts,
- uses abstract/headline fallback summaries (no LLM for this fast pass),
- caches by SHA256 over control values + row fingerprints.

### Step B: Publish quick fallback outputs immediately

Before heavy LLM calls:

- section briefs get deterministic fallback text (`_fallback_brief_from_packet`),
- Signal Studio gets deterministic quick workflow (`_build_fast_workflow`),
- UI switches to ready state quickly.

### Step C: Schedule full LLM pass

`_pending_agent_full` is set for background full upgrade.

## 8) Full multi-agent backend pass

`_run_full_agent_pipeline()` performs heavyweight path:

1. Rebuild packets with real summaries:
   - `_build_agent_section_packets(include_summaries=True)`
   - `_ensure_summaries_for_articles(...)` -> `get_summaries_parallel(...)`
2. Generate section briefs in parallel:
   - `generate_section_briefs(...)` -> `section_brief_agent.build_section_briefs(...)`
3. Run serial 3-agent workflow:
   - Agent 1: `analyze_cross_section_links(...)`
   - Agent 2: `evaluate_world_sentiment(...)`
   - Market snapshot: `fetch_market_snapshot()`
   - Agent 3: `validate_with_markets(...)`
4. Save final outputs to:
   - `section_brief_state`
   - `agent_workflow_state`
   - `agent_pipeline_cache`

Important: stale-run guard (`run_id`) prevents old async completions from overwriting newer state.

## 9) What each API is used for

- NYT API: fetch raw article feed by section.
- OpenAI API:
  - headline sentiment,
  - card summaries by tone,
  - impact labels,
  - section briefs,
  - Agent 1/2/3 reasoning and synthesis,
  - research brief modal agent.
- Yahoo Finance (`yfinance`):
  - market snapshot used by workflow and Agent 3 validation.

## 10) Research brief flow (per-card "Dive Deeper")

When a dive button is clicked:

1. URL is resolved from visible card.
2. `run_research_brief(...)` is called in background thread.
3. Research agent loops with OpenAI tool-calling (`wikipedia_lookup`, `yahoo_finance_quote`) up to max rounds.
4. Final text is displayed in modal and cached by URL/model/prompt fingerprint.

This flow is separate from the main 3-agent Signal Studio pipeline.

## 11) Failure behavior and fallbacks

- Missing `NYT_API_KEY`: empty feed path, refresh stops.
- NYT section failures: partial feed still allowed from successful sections.
- All NYT failures: may reuse short-lived NYT cache.
- Missing `OPENAI_API_KEY`: sentiment/impact/summaries and agent outputs degrade to rule-based or neutral fallbacks.
- Agent/full pipeline exceptions: quick fallback UI remains available; logs record errors.
- Market fetch issues: payload returns `unknown`-style summary instead of crashing.

## 12) Single-sentence backend summary

The backend uses a two-phase refresh (fast NYT publish first, AI enrichment second), then a quick deterministic Signal Studio snapshot followed by a full cached multi-agent LLM upgrade, all orchestrated through Shiny reactive effects and in-memory caches.
