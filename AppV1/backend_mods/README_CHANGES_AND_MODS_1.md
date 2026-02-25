# Changes and Mods 1 — Change Analysis Report

**Scope:** OLD = commit `69146de` (baseline), CURRENT = HEAD (main)  
**Repo:** DS-AIforSystemsEng-Project

---

## Part A — Change Analysis Report

### 1. Executive Summary

- **Structural:** New `.gitignore` (env, Python artifacts); removal of tracked `__pycache__/*.pyc`; no new top-level layout.
- **Functional:** Data flow refactor: refresh is explicit (button + initial load); sentiment and time filtering run on cached `enriched_articles_state`; no reactive recalculation on time/sentiment; sentiment filtering normalized (lowercase, NaN→neutral); empty/None handling standardized to empty DataFrames.
- **Performance:** Summary workers reduced (6→3); per-worker HTTP client reuse in `get_summaries_parallel`; sentiment batch order preserved via `(start_idx, batch)`; no new rate-limit logic.
- **API:** `fetch_nyt_articles` and `filter_by_time` no longer return `None` (return empty or fallback DataFrame); `get_summary` gains optional `client`; app no longer imports `get_sentiment` or `get_summary` (still used only inside `ai_services`).
- **Cosmetic / docs:** Logging added; comment/header tweaks; debug `print` in sentiment path; clearer "no articles" messages.

---

### 2. File-Level Diff Summary

| File | Lines + | Lines − | Type of change | Risk | Stability impact |
|------|----------|----------|----------------|------|-------------------|
| `AppV1/app.py` | ~221 | ~95 | Logic + refactor: refresh flow, state, filtering, null handling | **High** | Different reactivity; fewer re-fetches; clearer empty states |
| `AppV1/config.py` | ~63 | ~18 | Logic: multi-path `.env` loading, warnings | **Low** | More reliable env loading from different cwds |
| `AppV1/modules/data_fetch.py` | ~88 | ~45 | Logic: no None returns, logging, `filter_by_time` fallbacks | **Medium** | Callers must not rely on None; fallback "return all" if time filter fails |
| `AppV1/modules/ai_services.py` | ~106 | ~35 | Logic: order-safe sentiment batching, summary workers, client reuse, logging | **Medium** | Sentiment order correct; fewer concurrent summary requests |
| `AppV1/modules/categorization.py` | ~60 | ~25 | Logic: no None returns, `.empty` checks, guards for missing columns | **Low** | Safer with empty/malformed DataFrames |
| `.gitignore` | 15 | 2 | Config: env + Python ignores | **Low** | Repo hygiene only |
| `AppV1/__pycache__/*.pyc` (6 files) | 0 | (binary) | Deletion: bytecode removed from tracking | **Low** | Safe; should be ignored |

---

### 3. app.py Detailed Analysis

**Reactive blocks:**

| Block | OLD (69146de) | NEW (HEAD) |
|-------|----------------|------------|
| Loading on change | `@reactive.effect` + `@reactive.event(input.refresh, input.time_hours, input.sentiment)` → set loading true, show overlay | **Removed.** Loading only in `_run_refresh()`. |
| Clear loading | `@reactive.effect` depending on `filtered_articles()` → set loading false | **Removed.** Loading cleared in `_run_refresh()` `finally`. |
| Raw articles | `@reactive.calc` `raw_articles()`: depends on `input.refresh()`, fetches NYT, then `filter_by_time(arts, input.time_hours())` | **Removed.** Replaced by explicit refresh. |
| Enriched articles | `@reactive.calc` `enriched_articles()`: from `raw_articles()` → breaking, trending, sort_latest | **Removed.** Enrichment done inside `_run_refresh()`. |
| Articles with sentiment | `@reactive.calc` `articles_with_sentiment()`: from `enriched_articles()`, fills sentiment_cache, returns arts with sentiment | **Removed.** Sentiment fetched once in `_run_refresh()` and stored in `enriched_articles_state`. |
| **Refresh flow** | (Implicit: any change to refresh/time/sentiment triggered loading and recalculation of the calc chain.) | `@reactive.effect` `@reactive.event(input.refresh)` → `_run_refresh()` only. |
| **Initial load** | (First evaluation of calcs when NYT key present.) | `@reactive.effect` `_initial_load()`: once sets `initial_load_done`, runs `_run_refresh()`. |
| **Filter flow** | `@reactive.calc` `filtered_articles()`: from `articles_with_sentiment()`, then time + sentiment filter | `@reactive.calc` `filtered_articles()`: from `enriched_articles_state.get()`, then `filter_by_time(df, input.time_hours())`, then sentiment filter (normalized). |
| Pagination reset | `@reactive.effect` on `input.time_hours`, `input.sentiment` → `page_state.set({})` | `@reactive.effect` `_reset_pagination()` on same inputs → `page_state.set(dict())` only if current state is non-empty dict. |

**Sentiment flow:** OLD: reactive chain; sentiment filter used `arts["sentiment"].isin(s)` (no normalization). NEW: sentiment computed once per refresh in `_run_refresh()`, stored in `enriched_articles_state`; selection and column normalized (lowercase, NaN→neutral).

**Loading overlay:** OLD: show on any of refresh/time_hours/sentiment; hide when `filtered_articles()` evaluated. NEW: show/hide only inside `_run_refresh()` (start/finally). No overlay on time/sentiment change.

**Refresh behavior:** OLD: refresh + time/sentiment could trigger recalculation; time change triggered full refetch. NEW: refresh only on button or initial load; time/sentiment only filter cached data; no API on time/sentiment change.

**Behavior-breaking:** (1) Time/sentiment no longer trigger fetch or loading. (2) Pagination reset only when `page_state` is non-empty dict.

---

### 4. modules/data_fetch.py Diff Analysis

- **Concurrency:** Unchanged (ThreadPoolExecutor, 7 workers); success check changed from `len(df) > 0` to `not df.empty`.
- **Error handling:** OLD returned `None` on failure; NEW returns `pd.DataFrame()`, logs with `logger.exception`.
- **None-return:** OLD could return `None`; NEW never returns `None` (empty DataFrame or fallback `articles` in `filter_by_time`).
- **filter_by_time:** NEW adds missing `published_date` guard (return all + warning), try/except with fallback to full `articles` if mask empty or on exception.
- **Rate-limit:** No new retries or backoff; only logging.

---

### 5. modules/ai_services.py Diff Analysis

- **Sentiment batching:** OLD used a single `offset` with `as_completed` so completion order could misalign results; NEW uses `(start_index, batch)` so results match input order.
- **Ordering:** NEW guarantees order of results matches order of `titles`.
- **Parsing:** Unchanged.
- **Silent failure:** Same fallbacks; NEW adds one-time print + `_missing_key_warned`, and `logger.warning`/`logger.exception`.
- **get_summary / get_summaries_parallel:** NEW adds optional `client`; `get_summaries_parallel` uses 3 workers and per-worker client reuse (order preserved).

---

### 6. Configuration Changes

- **config.py:** OLD: single path (project root `.env`). NEW: `find_dotenv` + walk up from AppV1 + `load_dotenv(override=False)`; logs loaded paths; warns on missing keys.
- **.gitignore:** NEW adds `.env.local`, `__pycache__/`, `*.py[cod]`, etc. No secrets in code; same env vars.
- **.pyc:** Six `__pycache__/*.pyc` removed from tracking; safe cleanup.

---

### 7. Deleted / Removed Files

All removed files are `AppV1/**/__pycache__/*.pyc` (9 files). Safe removal; bytecode only.

---

### 8. Behavioral Impact Assessment

- **Sentiment filtering:** NEW normalizes selection and column (lowercase, NaN→neutral); stricter matching.
- **Refresh vs API frequency:** NEW does fewer API calls overall: time/sentiment changes cause no calls; refresh always does one full sentiment batch (cache cleared each refresh).
- **429 risk:** Summary concurrency 6→3; no new rate-limit logic.
- **Caching:** Sentiment cache cleared each refresh in NEW; summary cache unchanged.

---

### 9. Redundant / Dead Logic

- **Removed in new:** `get_sentiment`/`get_summary` no longer imported in app (still used in ai_services). Reactive loading effects and calc chain replaced by `_run_refresh` + `enriched_articles_state`.
- **New but noisy:** Debug `print`s in app and ai_services (sentiment, API key, status); can be removed for production.
- **Possible regressions:** `filter_by_time` returning all articles when time window is empty or on error (OLD could return empty); missing `published_date` returns all articles in NEW.

---

### 10. Overall Architectural Health Score

| Criterion | OLD (69146de) | NEW (HEAD) |
|-----------|----------------|------------|
| **Score** | **5/10** | **7/10** |
| Null safety | Many `None` returns | Consistent empty DataFrame |
| Reactivity | Loading/fetch tied to time/sentiment | Explicit refresh; time/sentiment filter only |
| Sentiment order | Parallel could misassign | Order preserved by batch index |
| Observability | Little logging | Logging + warnings |
| Config | Single .env path | Multi-path .env, warnings |
| Repo hygiene | .pyc tracked | .gitignore + .pyc removed |

**Justification:** OLD had fragile nulls and time-slider-triggered refetches; NEW fixes null contract, ordering, and refresh semantics at the cost of documented behavior changes (refresh-only fetch; time-filter fallbacks).

---

## Part B — Hidden Behavioral Differences

Execution paths for four user actions (OLD vs NEW).

### 1. Refresh click

**OLD:** `input.refresh` → show loading → `raw_articles()` recomputes (1 NYT fetch, `filter_by_time`) → `enriched_articles()` → `articles_with_sentiment()` (sentiment only for URLs not in cache) → `filtered_articles()` → clear loading. **Result:** 1 NYT fetch, 0–1 sentiment batch (only uncached URLs).

**NEW:** `input.refresh` → `_run_refresh()`: clear sentiment cache, show loading, 1 NYT fetch, full pipeline, **full sentiment batch for all URLs**, set `enriched_articles_state`, hide loading. **Result:** 1 NYT fetch, 1 full sentiment batch every time.

**Difference:** NEW always runs sentiment for every article on refresh; OLD reused cache across refreshes.

---

### 2. Sentiment filter toggle

**OLD:** `input.sentiment()` → show loading → `filtered_articles()` recomputes (filter only, no API) → clear loading → pagination reset. **Result:** Loading flashes; no API; pagination resets.

**NEW:** `input.sentiment()` → `filtered_articles()` recomputes (same state, new filter) → `_reset_pagination` (reset if non-empty). **Result:** No loading overlay; no API; pagination resets.

**Difference:** OLD showed loading briefly; NEW does not.

---

### 3. Time slider change

**OLD:** `input.time_hours()` → show loading → **`raw_articles()` invalidated → full `fetch_nyt_articles()` again** → `filter_by_time(arts, new_hours)` → chain recomputes → clear loading → pagination reset. **Result:** **Full NYT refetch on every time change.** Loading shown.

**NEW:** `input.time_hours()` → `filtered_articles()` recomputes from **same** `enriched_articles_state` → `filter_by_time(df, new_hours)` in memory only → `_reset_pagination`. **Result:** No API calls; no loading overlay.

**Difference:** OLD refetched from NYT on every time change; NEW only filters cached data. Largest hidden behavioral change.

---

### 4. Pagination click (Next)

**OLD:** `input.next_*` → `update_page(cat)` → `page_state` updated → outputs re-run; `make_cards_ui` may call `get_summaries_parallel` for new cards. No loading; no NYT/sentiment refetch.

**NEW:** Same: `update_page(cat)`, same cache and summary logic; added guards for empty frames and `page_state`. No loading; no NYT/sentiment refetch.

**Difference:** None material; pagination and summary fetching align.

---

### Summary table

| User action        | OLD: API calls              | OLD: Loading   | NEW: API calls              | NEW: Loading   |
|--------------------|-----------------------------|----------------|-----------------------------|----------------|
| **Refresh**        | 1 NYT, 0–1 sentiment batch  | Yes            | 1 NYT, 1 full sentiment     | Yes            |
| **Sentiment toggle** | None                       | Brief flash    | None                        | None           |
| **Time slider**    | **1 NYT fetch every time**  | Yes            | **None** (in-memory only)   | None           |
| **Pagination**     | None (summaries if needed)  | No             | None (summaries if needed)  | No             |

---

**End of Changes and Mods 1**
