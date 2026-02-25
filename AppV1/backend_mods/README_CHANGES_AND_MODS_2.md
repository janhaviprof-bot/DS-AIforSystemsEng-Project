# Changes and Mods 2 — Change Analysis Report

**Scope:** OLD = current GitHub repo (commit `a02366a` — "Add detailed change analysis report (README_CHANGES_AND_MODS_1)"); NEW = current local (uncommitted changes as of report date).  
**Repo:** DS-AIforSystemsEng-Project

---

## Part A — Change Analysis Report

### 1. Executive Summary

- **Structural:** Sports tab and section removed (UI, config, handlers, categorization); new module `impact_classifier.py`; new files `.env.example`, `AppV1/SETUP_ENV.md`; `.gitignore` adds `.DS_Store`.
- **Functional:** Impact classification (LLM, TTL cache) added and stored in `impact_label`; sentiment toggle filters by `sentiment` column; category tabs fall back to time+category when sentiment filter would leave a tab empty; loading overlay uses async-safe `_send_loading()`; OPENAI key validated at startup; time slider 6–60 hrs (default 60); duplicate `@reactive.effect` on next_arts removed (fixes "Effect_ object is not callable").
- **Diagnostics:** REFRESH/TIME_FILTER/SENTIMENT_FILTER/CATEGORY_FILTER stage logging; per-section NYT warnings when a section returns 0 articles; impact classifier logging (API status, batch distribution, cache vs classify).
- **API / config:** `NYT_SECTIONS` no longer includes `"sports"`; category filter uses normalized (strip, lower) section/category; no change to refresh architecture or caching design beyond impact TTL.

---

### 2. File-Level Diff Summary

| File | Lines + | Lines − | Type of change | Risk | Stability impact |
|------|----------|----------|----------------|------|-------------------|
| `AppV1/app.py` | ~243 | ~58 | Logic: impact integration, async loading, diagnostics, Sports removed, category fallback, time 60hrs | **High** | Sentiment filter and category fallback; async fixes; no Sports tab |
| `AppV1/config.py` | 0 | 1 | Config: remove `"sports"` from `NYT_SECTIONS` | **Low** | Fewer API requests; no sports section |
| `AppV1/modules/categorization.py` | ~19 | ~3 | Logic: category/section normalized (strip, lower) | **Low** | More reliable category matching |
| `AppV1/modules/data_fetch.py` | ~7 | 0 | Diagnostics: warn when no articles from any section; log sections that returned 0 | **Low** | Visibility only |
| `.gitignore` | 1 | 0 | Config: add `.DS_Store` | **Low** | Repo hygiene |
| **New** `AppV1/modules/impact_classifier.py` | ~254 | 0 | New module: impact batch/parallel, TTL cache, `get_impacts_for_articles` | **Medium** | New LLM path; fallback to neutral on failure |
| **New** `.env.example` | ~7 | 0 | Template for `.env` (keys not committed) | **Low** | Onboarding only |
| **New** `AppV1/SETUP_ENV.md` | ~44 | 0 | Setup instructions for API keys and run | **Low** | Docs only |

---

### 3. app.py Detailed Analysis

**Reactive / flow changes (vs GitHub a02366a):**

| Area | OLD (a02366a) | NEW (local) |
|------|----------------|-------------|
| Refresh / loading | Sync `_run_refresh()`; `session.send_custom_message` direct | Async `_run_refresh()`; `_send_loading(show)` with `asyncio.iscoroutine` check; `_refresh_flow` / `_initial_load` async and `await _run_refresh()` |
| Time slider | 6–48 hrs, default 24 | 6–60 hrs, default 60 |
| Sentiment filter | Filter by sentiment (unchanged) | Still filters by `sentiment`; added SENTIMENT_FILTER stage logging |
| Category tabs | `category_articles_for` = filter_by_category(filtered_articles(), cat) | Same plus **fallback**: if category result empty, use `time_filtered_articles()` + `filter_by_category` so tab shows something |
| New calc | — | `time_filtered_articles()`: time filter only (no sentiment), used for fallback |
| Impact | — | After sentiment, `get_impacts_for_articles(arts, api_key)`; `arts["impact_label"]` set (or neutral on failure); FILTER_BASE logs impact_label_distribution |
| Sports | Nav panel, next_sports, news_sports | **Removed** (tab, handler, render) |
| Startup | — | `_log_openai_key_once()`: log OPENAI key loaded (length) or missing |
| Pagination effect | — | **Fix:** next_arts had duplicate `@reactive.effect`; one removed to fix "Effect_ object is not callable" |

**Empty-state messages:** Clearer copy (no articles loaded vs no match for sentiment vs category/time); `cat_label` used in message for category-specific text.

**Diagnostics added:** REFRESH (raw count, section_distribution, fetched_from_section_distribution, published_date_range); TIME_FILTER (before/after rows, section_distribution, sentiment_distribution); SENTIMENT_FILTER (filter values, rows before/after); CATEGORY_FILTER (category, rows before/after, fallback when used).

---

### 4. modules/impact_classifier.py (New Module)

- **Purpose:** LLM-based impact classification (positive / negative / neutral) from title, subtitle, abstract; separate from `ai_services`; impact = societal benefit/harm, not tone.
- **`get_impact_batch(items, api_key)`:** Up to 10 items per request; items = (url, title, subtitle, abstract); returns list of labels; updates global `impact_cache` by URL; on missing key or API failure logs ERROR/warning and falls back to neutral.
- **`get_impact_parallel(items, api_key)`:** Batches of 10, max 3 workers; preserves order.
- **`get_impacts_for_articles(arts, api_key)`:** For each URL, use cache if valid (TTL 30 min); else classify; only calls LLM for cache miss or expired; returns list of labels in arts order.
- **TTL cache:** `impact_cache[url] = {"label", "timestamp"}`; reclassify only if `current_time - timestamp > 30` minutes.
- **Logging:** API status, model, n_items, parsing_ok, label_distribution per batch; classification triggered vs all from cache; no silent neutral masking without strong logging.

---

### 5. modules/data_fetch.py Diff

- **New:** If no section returns articles: `logger.warning("NYT API returned no articles from any section (check API key and network)")`.
- **New:** After building combined, log which requested sections have 0 articles in result: `logger.warning("NYT API returned 0 articles for section '%s'", sec)` for each missing section.
- No change to concurrency, None behavior, or `filter_by_time` logic.

---

### 6. modules/categorization.py Diff

- **filter_by_category:** Category and section/fetched_from_section normalized: `str(category).strip().lower()`; section/fetched series use `.str.strip().str.lower()` so "Sports" vs "sports" and whitespace no longer cause mismatches.
- Sports-specific keyword expansion (SPORTS_KEYWORDS and sports branch) **removed** in Mods 2 because the Sports tab was removed.

---

### 7. Configuration and Repo

- **config.py:** `"sports"` removed from `NYT_SECTIONS`.
- **.gitignore:** `.DS_Store` added.
- **New files (untracked):** `.env.example` (placeholder keys for NYT/OpenAI); `AppV1/SETUP_ENV.md` (where to put keys, how to run, Refresh note).

---

### 8. Deleted / Removed (vs GitHub)

| Item | Safe removal? |
|------|----------------|
| Sports nav panel, `news_sports`, `next_sports` handler | Yes; tab no longer desired. |
| Sports in `NYT_SECTIONS` | Yes; no sports fetch. |
| Sports in `CATEGORIES` | Yes. |
| Sports keyword logic in categorization | Yes; no Sports tab to serve. |

---

### 9. Behavioral Impact

- **Sentiment toggle:** Still filters by `sentiment` column; no change to when API is called (only on refresh). Clearer empty message when no articles match.
- **Category tabs:** If sentiment filter would leave a category empty, that tab now shows time+category (all sentiments) so the tab is not blank.
- **Time range:** Default 60 hrs and max 60 hrs; more articles in window by default.
- **Impact:** New column `impact_label`; computed on refresh (or TTL expiry); failure or missing key → neutral for all; no extra LLM on time/sentiment change.
- **Loading overlay:** Async-safe; no "coroutine was never awaited" when Shiny uses async `send_custom_message`.
- **Crash fix:** Duplicate `@reactive.effect` on next_arts caused "Effect_ object is not callable"; removing the duplicate restores stable run after refresh.

---

### 10. Hidden Behavioral Differences (Mods 2)

| User action | OLD (a02366a) | NEW (local) |
|-------------|----------------|-------------|
| **Refresh** | Sync refresh; loading via send_custom_message (could warn if async) | Async refresh; loading via _send_loading (awaits if coroutine). Impact classification run; impact_label set. |
| **Sentiment toggle** | Filters by sentiment; empty category tab could show "no match" message | Same filter; if category would be empty, **fallback** shows time+category (all sentiments) so tab shows content. |
| **Time slider** | 6–48, default 24 | 6–60, default 60. |
| **Category tab (e.g. arts)** | Only articles matching time + sentiment + category | Same, or if that's empty then time + category (all sentiments). |
| **Sports tab** | Present | **Removed.** |

---

### 11. Overall Architectural Health (Mods 2 vs GitHub)

| Criterion | GitHub (a02366a) | Local (Mods 2) |
|-----------|-------------------|-----------------|
| **Observability** | Basic logging | Stage-wise REFRESH/TIME/SENTIMENT/CATEGORY + impact batch logs; section-level NYT warnings. |
| **Resilience** | Sentiment/impact not separated; loading sync-only | Impact in own module; fallback to neutral; category fallback so tabs not blank; async loading fixed. |
| **UX** | Sports tab; 48 hr max; 24 hr default | No Sports; 60 hr default/max; clearer empty states. |
| **Stability** | Possible Effect_ crash (duplicate decorator) | Fixed. |

**Summary:** Mods 2 add impact classification, diagnostics, category fallback, Sports removal, time-range and async/effect fixes without changing refresh architecture or caching design. Dashboard is more observable and robust.

---

**End of Changes and Mods 2**
