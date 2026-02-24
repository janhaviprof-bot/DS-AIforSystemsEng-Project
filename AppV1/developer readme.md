# News for People in a Hurry

## Introduction

**News for People in a Hurry** is a web app that shows top New York Times stories in a quick, scannable format. Browse by category (ALL, business, sports, arts, technology, world, politics), see breaking and trending highlights, and read short AI-generated summaries instead of full articles. Use the controls on the left to filter by time (6–48 hours), sentiment (positive, negative, neutral), and summary tone (Informational, Opinion, Analytical). Click **Refresh News** to load the latest, and **Next** to see more cards.

---

## Developer Guide

### Overview

The app is built with **Shiny for Python** and uses the NYT Top Stories API and OpenAI for sentiment and summaries.

### Layout

- **Left (1/4):** Control panel – time slider, sentiment checkboxes, tone dropdown, Refresh button  
- **Right (3/4):** Category tabs and news cards in a 3-column grid

### Project Structure

```
AppV1/
├── app.py              # Main Shiny app entry
├── config.py           # Load .env, export API keys
├── modules/
│   ├── data_fetch.py   # NYT API
│   ├── categorization.py
│   ├── ai_services.py  # OpenAI sentiment & summary
│   └── news_cards.py   # Card UI helpers
├── data/
│   └── fun_facts.py    # 50 fun facts for loading overlay
├── www/
│   └── placeholder.svg # Fallback image when no multimedia
├── requirements.txt
├── developer readme.md # This file
└── README.md
```

### Environment Setup

#### 1. Python

- Python 3.10+ recommended  
- Create and activate a virtual environment (optional but recommended)

#### 2. Install Dependencies

From the project root or `AppV1`:

```bash
cd AppV1
pip install -r requirements.txt
```

Dependencies: `shiny`, `httpx`, `python-dotenv`, `pandas`.

#### 3. API Keys

API keys are loaded from the **project root** `.env` file:

```
DS-AIforSystemsEng-Project/
├── .env          # <-- Create this file here (project root)
├── AppV1/
│   ├── app.py
│   └── ...
```

Create `.env` at the project root with:

```env
NYT_API_KEY=your_nytimes_api_key
OPENAI_API_KEY=your_openai_api_key
```

**NYT API key**

- Register at [developer.nytimes.com](https://developer.nytimes.com/)
- Create an app and use the Top Stories API key

**OpenAI API key**

- Create at [platform.openai.com](https://platform.openai.com/api-keys)

#### 4. Run the App

```bash
cd AppV1
python app.py
```

Or:

```bash
cd AppV1
shiny run app.py
```

The app starts on `http://127.0.0.1:8000` and can open in the browser automatically.

---

### Architecture and Data Flow

The app uses Shiny's **reactive** model. Data flows through reactive calcs; changes to inputs invalidate downstream calcs.

```
raw_articles()          → NYT fetch, filter by time
    ↓
enriched_articles()     → add_breaking_tag, compute_trending_score, sort_latest
    ↓
articles_with_sentiment() → OpenAI batch sentiment (cached)
    ↓
filtered_articles()     → filter by sentiment checkbox
    ↓
category_articles_for(cat) → filter by tab (ALL or section)
    ↓
current_cards_for(cat)  → select_first_six or select_next_six (pagination)
    ↓
make_cards_ui(cat)      → build cards, fetch summaries (cached), render
```

**Triggers that reset loading:**

- `input.refresh`, `input.time_hours`, `input.sentiment` → `show_loading`
- Cards ready or `filtered_articles()` ready → `hide_loading` (also tied to Shiny `shiny:idle`)

---

### Module Reference

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `config.py` | Load `.env` from project root, export `NYT_API_KEY`, `OPENAI_API_KEY`, `NYT_SECTIONS` | — |
| `modules/data_fetch.py` | Fetch NYT Top Stories, merge sections, filter by time | `fetch_nyt_articles()`, `filter_by_time()` |
| `modules/categorization.py` | Breaking/trending/latest logic, category filter, pagination | `add_breaking_tag()`, `compute_trending_score()`, `sort_latest()`, `filter_by_category()`, `select_first_six()`, `select_next_six()` |
| `modules/ai_services.py` | OpenAI sentiment and summary | `get_sentiments_parallel()`, `get_summaries_parallel()`, `get_summary()` |
| `modules/news_cards.py` | Card UI and image URL from multimedia | `get_image_url()`, `news_card_ui()` |
| `data/fun_facts.py` | List of 50 fun facts for loading overlay | `FUN_FACTS` |

---

### Article DataFrame Columns

Columns added or used across the pipeline:

| Column | Source | Description |
|--------|--------|-------------|
| `url` | NYT | Unique article ID |
| `title`, `abstract`, `subtitle`, `section` | NYT | Article metadata |
| `published_date`, `updated_date` | NYT | Datetimes (UTC) |
| `multimedia` | NYT | List of images; used for card image and trending score |
| `des_facet` | NYT | List of subject facets; used for trending score |
| `n_sections` | data_fetch | Number of sections containing this article |
| `fetched_from_section` | data_fetch | Section(s) fetched from |
| `is_breaking` | categorization | `published_date` within 2 hours |
| `trending_score`, `is_trending` | categorization | Score > 0.5 → trending |
| `sentiment` | ai_services | positive / negative / neutral |

---

### API Reference

**NYT Top Stories**

- Base URL: `https://api.nytimes.com/svc/topstories/v2/{section}.json?api-key={key}`
- Sections in `config.NYT_SECTIONS`: home, business, sports, arts, technology, world, politics
- Docs: [developer.nytimes.com/docs/top-stories-product](https://developer.nytimes.com/docs/top-stories-product/1/overview)

**OpenAI**

- Chat completions: `https://api.openai.com/v1/chat/completions`
- Models: `gpt-3.5-turbo` (sentiment and summary)
- Sentiment: batch of titles → list of "positive"/"negative"/"neutral"
- Summary: (title, abstract, subtitle, tone) → 2–3 line summary

---

### Caching

| Cache | Location | Key | Cleared when |
|-------|----------|-----|--------------|
| `sentiment_cache` | server | article `url` | Session end |
| `summary_cache` | server | `{url}|{tone}` | Session end |

Caches persist for the session only. Changing tone triggers new summaries (different cache key).

---

### Loading Overlay

- **HTML:** Static overlay (`#static-loading-wrap`) with spinner and fact container.
- **JS:** `startFactRotation()` shuffles facts and rotates every 7 seconds. `stopLoadingOverlay()` clears interval, pauses animations, hides overlay. `restartLoadingOverlay()` shows overlay and starts rotation.
- **Shiny events:** `$(document).on("shiny:idle", stopLoadingOverlay)` and `$(document).on("shiny:busy", restartLoadingOverlay)` keep overlay in sync with Shiny's pulse.
- **Custom messages:** `hide_loading` and `show_loading` call the same functions as fallback.

---

### How to Extend

**Add a new category tab**

1. Add section name to `config.NYT_SECTIONS` if it is a new NYT section.
2. Add category to `CATEGORIES` in `app.py`.
3. Add `ui.nav_panel("section", ui.output_ui("news_section"), ui.input_action_button("next_section", "Next"))` to `ui.navset_tab`.
4. Add `@render.ui def news_section(): return make_cards_ui("section")`.
5. Add `@reactive.effect` + `@reactive.event(input.next_section)` calling `update_page("section")`.

**Add a new control**

1. Add `ui.input_*` in the sidebar.
2. Use `input.new_control()` in a reactive calc or effect.
3. Add `input.new_control` to `_set_loading_on_change` event list if it should trigger a full refresh.
4. Add to the effect that resets `page_state` (e.g. `input.time_hours`, `input.sentiment`) if it changes filters.

**Change trending/breaking logic**

- Edit `modules/categorization.py`: `add_breaking_tag`, `compute_trending_score`, `select_first_six`, `select_next_six`.

**Add a new API or data source**

- Add a module under `modules/`, e.g. `modules/my_service.py`.
- Call it from a reactive calc in `app.py` (similar to `raw_articles` / `enriched_articles`).

---

### Conventions

- **Reactive calcs:** Use `@reactive.calc` for derived data; they re-run when dependencies change.
- **Effects:** Use `@reactive.effect` + `@reactive.event()` for side effects (e.g. update page_state, send messages).
- **Page state:** `page_state` is a `reactive.value(dict())` storing `{category: page_num, f"{category}_used": [urls]}`.
- **Badges:** Only page 1; slots 0–1 = BREAKING, 2–3 = TRENDING. Badge area has fixed min-height to avoid layout shift.
- **Static assets:** Place files in `www/`; served at `/www/`. `placeholder.svg` is used when article has no image.

---

### Troubleshooting

| Symptom | Likely cause |
|--------|--------------|
| "No articles found" | Missing `NYT_API_KEY`, invalid key, or no articles in time window |
| Summaries show abstract instead of AI text | Missing or invalid `OPENAI_API_KEY`; falls back to abstract |
| Loading overlay never hides | Check browser console; ensure Shiny `shiny:idle` fires or `hide_loading` is sent |
| Pagination shows same cards | `page_state` keys must match category exactly; check `update_page()` and `current_cards_for()` |

---

### Notes for Developers

- `.env` is ignored by git; do not commit keys.
- `config.py` loads `.env` from the parent of `AppV1` (project root).
- Sentiment and summaries are cached to reduce API calls.
- The loading overlay uses Shiny `shiny:busy` and `shiny:idle` to stay in sync with the pulse indicator.
