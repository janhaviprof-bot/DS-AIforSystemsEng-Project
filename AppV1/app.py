# News for People in Hurry - Shiny for Python (refactored for stability)
# Run: shiny run app.py

from pathlib import Path
import asyncio
import logging

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
import json
import pandas as pd

from config import NYT_API_KEY, OPENAI_API_KEY, NYT_SECTIONS
from modules.data_fetch import fetch_nyt_articles, filter_by_time
from modules.categorization import (
    add_breaking_tag,
    compute_trending_score,
    sort_latest,
    filter_by_category,
    select_first_six,
    select_next_six,
)
from modules.ai_services import get_summaries_parallel, get_sentiments_parallel
from modules.impact_classifier import get_impacts_for_articles
from modules.news_cards import get_image_url, news_card_ui

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Startup: validate OPENAI_API_KEY (length only, never log value)
_openai_key_checked = False
def _log_openai_key_once():
    global _openai_key_checked
    if _openai_key_checked:
        return
    _openai_key_checked = True
    key = OPENAI_API_KEY
    if key and str(key).strip():
        logger.info(
            "OPENAI_API_KEY loaded: length=%s (set, non-empty). Impact and sentiment classification enabled.",
            len(str(key).strip()),
        )
    else:
        logger.warning(
            "OPENAI_API_KEY is missing or empty at startup. Set it in .env (project root or AppV1). Impact/sentiment will fallback to neutral."
        )

try:
    from data.fun_facts import FUN_FACTS
except ImportError:
    FUN_FACTS = ["Loading your news…"]

CATEGORIES = ["ALL", "business", "arts", "technology", "world", "politics"]

# Static loading overlay - visible immediately on page load, before Shiny connects
LOADING_HTML = f'''<div id="loading-overlay-root" class="loading-overlay" style="pointer-events:auto;">
<div style="position:relative;display:flex;align-items:center;justify-content:center;">
<div class="loading-spinner"></div>
<div class="loading-spinner loading-spinner-2"></div>
</div>
<div id="loading-fact-container"><span id="loading-fact" class="loading-fact fade-in">{FUN_FACTS[0] if FUN_FACTS else "Loading your news…"}</span></div>
<p style="color:#6B6B6B;font-size:0.9rem;">Loading your news…</p>
</div>
<script>
(function() {{
  window._loadingFactInterval = null;
  window._loadingFacts = {json.dumps(FUN_FACTS)};
  window._loadingFactIdx = 0;
  function shuffle(arr) {{
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {{
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }}
    return a;
  }}
  window.startFactRotation = function() {{
    if (window._loadingFactInterval) clearInterval(window._loadingFactInterval);
    var el = document.getElementById("loading-fact");
    if (!el || !window._loadingFacts.length) return;
    window._loadingFacts = shuffle(window._loadingFacts);
    el.textContent = window._loadingFacts[0];
    window._loadingFactIdx = 0;
    window._loadingFactInterval = setInterval(function() {{
      window._loadingFactIdx = (window._loadingFactIdx + 1) % window._loadingFacts.length;
      el.textContent = window._loadingFacts[window._loadingFactIdx];
      el.classList.remove("fade-in");
      el.offsetHeight;
      el.classList.add("fade-in");
    }}, 7000);
  }};
  window.startFactRotation();
}})();
</script>'''

# UI
app_ui = ui.page_fluid(
    ui.HTML(f'<div id="static-loading-wrap" style="position:fixed;inset:0;z-index:9999;">{LOADING_HTML}</div>'),
    ui.tags.head(
        ui.tags.style(
            """
            .news-card { border: 1px solid #ddd; border-radius: 8px; margin-bottom: 16px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; flex-direction: column; }
            .news-card .card-badge-area { min-height: 24px; padding: 4px 12px; }
            .news-card .card-badge-area .badge-placeholder { visibility: hidden; font-size: 0.75em; }
            .news-card .card-image { width: 100%; height: 180px; object-fit: cover; }
            .news-card .card-body { padding: 12px; flex: 1; display: flex; flex-direction: column; }
            .news-card .card-title { margin: 0 0 8px 0; font-size: 1.1em; }
            .news-card .card-summary { font-size: 0.9em; color: #444; margin-bottom: 8px; line-height: 1.4; flex: 1; }
            .news-card .card-link-wrap { text-align: right; margin-top: auto; }
            .news-card .card-link { color: #0066cc; }
            .badge-breaking { background: #c0392b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; }
            .badge-trending { background: #2980b9; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; }
            .news-cards-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
            .loading-overlay { position: fixed; inset: 0; z-index: 9999; background: rgba(247,244,239,0.95);
                display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2rem; }
            .loading-spinner { width: 64px; height: 64px; border: 4px solid rgba(166,30,30,0.3);
                border-top-color: #A61E1E; border-radius: 50%; animation: spin 0.8s linear infinite; }
            .loading-spinner-2 { width: 64px; height: 64px; border: 4px solid transparent;
                border-bottom-color: rgba(166,30,30,0.5); border-radius: 50%;
                animation: spin 1.5s linear infinite reverse; position: absolute; }
            @keyframes spin { to { transform: rotate(360deg); } }
            .loading-fact { text-align: center; color: #6B6B6B; font-size: 1.1rem; max-width: 32rem;
                line-height: 1.6; padding: 0 1rem; }
            .loading-fact.fade-in { animation: fadeIn 0.5s ease-out; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
            """
        ),
        ui.tags.script("""
            function stopLoadingOverlay() {
                if (window._loadingFactInterval) {
                    clearInterval(window._loadingFactInterval);
                    window._loadingFactInterval = null;
                }
                var el = document.getElementById("static-loading-wrap");
                if (el) {
                    el.style.animationPlayState = "paused";
                    el.querySelectorAll("*").forEach(function(n) { n.style.animationPlayState = "paused"; });
                    el.style.display = "none";
                }
            }
            function restartLoadingOverlay() {
                var el = document.getElementById("static-loading-wrap");
                if (el) {
                    el.style.display = "block";
                    el.style.animationPlayState = "";
                    el.querySelectorAll("*").forEach(function(n) { n.style.animationPlayState = ""; });
                    if (window.startFactRotation) window.startFactRotation();
                }
            }
            $(document).on("shiny:idle", stopLoadingOverlay);
            $(document).on("shiny:busy", restartLoadingOverlay);
            Shiny.addCustomMessageHandler("hide_loading", stopLoadingOverlay);
            Shiny.addCustomMessageHandler("show_loading", restartLoadingOverlay);
        """),
    ),
    ui.panel_title("News for People in Hurry"),
    ui.layout_sidebar(
        ui.sidebar(
            ui.h4("Controls"),
            ui.input_slider("time_hours", "Time range (hours back, 6–60; default 60)", 6, 60, value=60, step=1),
            ui.input_checkbox_group(
                "sentiment",
                "Sentiment (filter: positive / negative / neutral; leave unselected to show all)",
                choices=["positive", "negative", "neutral"],
                inline=True,
            ),
            ui.input_select(
                "tone",
                "Classify Tone",
                choices=["Informational", "Opinion", "Analytical"],
                selected="Informational",
            ),
            ui.input_action_button("refresh", "Refresh News"),
            title="Controls",
            width=350,
            open="always",
        ),
        ui.navset_tab(
            ui.nav_panel("ALL", ui.output_ui("news_all"), ui.input_action_button("next_all", "Next")),
            ui.nav_panel("business", ui.output_ui("news_business"), ui.input_action_button("next_business", "Next")),
            ui.nav_panel("arts", ui.output_ui("news_arts"), ui.input_action_button("next_arts", "Next")),
            ui.nav_panel("technology", ui.output_ui("news_technology"), ui.input_action_button("next_technology", "Next")),
            ui.nav_panel("world", ui.output_ui("news_world"), ui.input_action_button("next_world", "Next")),
            ui.nav_panel("politics", ui.output_ui("news_politics"), ui.input_action_button("next_politics", "Next")),
            id="category_tabs",
            selected="ALL",
        ),
    ),
)


def server(input: Inputs, output: Outputs, session: Session):
    _log_openai_key_once()
    sentiment_cache: dict = {}
    summary_cache: dict = {}
    page_state = reactive.value(dict())
    is_loading = reactive.value(False)
    initial_load_done = reactive.value(False)
    # Enriched articles (with sentiment + impact_label) — updated only on refresh
    enriched_articles_state = reactive.value(pd.DataFrame())

    async def _send_loading(show: bool):
        """Call send_custom_message; await if it returns a coroutine (Shiny async)."""
        msg = "show_loading" if show else "hide_loading"
        out = session.send_custom_message(msg, {})
        if asyncio.iscoroutine(out):
            await out

    async def _run_refresh():
        sentiment_cache.clear()
        if is_loading.get():
            return
        is_loading.set(True)
        await _send_loading(True)
        try:
            if not NYT_API_KEY or not str(NYT_API_KEY).strip():
                logger.warning("NYT_API_KEY missing; skipping fetch")
                enriched_articles_state.set(pd.DataFrame())
                return
            raw = fetch_nyt_articles(NYT_SECTIONS, NYT_API_KEY)
            if raw is None or raw.empty:
                logger.warning("fetch_nyt_articles returned no data (check API key and network)")
                enriched_articles_state.set(pd.DataFrame())
                return
            # ---- Refresh stage diagnostics ----
            total_raw = len(raw)
            sec_counts = {}
            fetched_counts = {}
            if "section" in raw.columns:
                sec_series = (
                    raw["section"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )
                sec_counts = sec_series.value_counts().to_dict()
            if "fetched_from_section" in raw.columns:
                fetched_series = (
                    raw["fetched_from_section"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )
                fetched_counts = fetched_series.value_counts().to_dict()
            published_min = None
            published_max = None
            if "published_date" in raw.columns:
                pub = pd.to_datetime(raw["published_date"], utc=True, errors="coerce")
                if not pub.empty:
                    published_min = str(pub.min())
                    published_max = str(pub.max())
            logger.info(
                "REFRESH stage: fetched raw articles count=%s section_distribution=%s fetched_from_section_distribution=%s published_date_range=%s..%s",
                total_raw,
                sec_counts,
                fetched_counts,
                published_min,
                published_max,
            )
            if "published_date" in raw.columns:
                raw = raw.copy()
                raw["published_date"] = pd.to_datetime(raw["published_date"], utc=True, errors="coerce")
            arts = add_breaking_tag(raw)
            if arts.empty:
                enriched_articles_state.set(pd.DataFrame())
                return
            arts = compute_trending_score(arts)
            arts = sort_latest(arts)
            if arts.empty:
                enriched_articles_state.set(pd.DataFrame())
                return
            # Sentiment once during refresh
            if "url" not in arts.columns or "title" not in arts.columns:
                enriched_articles_state.set(arts)
                return
            to_fetch = [u for u in arts["url"].tolist() if u not in sentiment_cache]
            if to_fetch:
                title_by_url = arts.set_index("url")["title"]
                titles = [str(title_by_url.loc[u]) for u in to_fetch]
                sentiments_list = get_sentiments_parallel(titles, OPENAI_API_KEY)
                for u, s in zip(to_fetch, sentiments_list):
                    sentiment_cache[u] = s
            arts = arts.copy()
            arts["sentiment"] = [sentiment_cache.get(u, "neutral") for u in arts["url"]]
            logger.info(
                "FILTER_BASE stage: sentiment_distribution_before_filter=%s",
                arts["sentiment"].value_counts().to_dict(),
            )
            # Impact classification (TTL cache); on failure keep neutral so dashboard still works
            try:
                api_key = OPENAI_API_KEY
                if api_key and str(api_key).strip():
                    logger.info("Refresh: calling get_impacts_for_articles with API key (length=%s)", len(str(api_key).strip()))
                    impact_labels = get_impacts_for_articles(arts, api_key)
                    arts["impact_label"] = impact_labels
                    logger.info("FILTER_BASE stage: impact_label_distribution=%s", pd.Series(impact_labels).value_counts().to_dict())
                else:
                    arts["impact_label"] = ["neutral"] * len(arts)
            except Exception as ie:
                logger.warning("Impact classification failed; using neutral for all: %s", ie)
                arts["impact_label"] = ["neutral"] * len(arts)
            enriched_articles_state.set(arts)
            logger.info("Enriched and stored %s articles", len(arts))
        except Exception as e:
            logger.exception("Refresh failed: %s", e)
            enriched_articles_state.set(pd.DataFrame())
        finally:
            is_loading.set(False)
            await _send_loading(False)

    # ---- Refresh flow: on button click ----
    @reactive.effect
    @reactive.event(input.refresh)
    async def _refresh_flow():
        await _run_refresh()

    # ---- Initial load: run once when dashboard first opens ----
    @reactive.effect
    async def _initial_load():
        if initial_load_done.get():
            return
        initial_load_done.set(True)
        await _run_refresh()

    # ---- Time-only filter (used for fallback when sentiment filter would hide a category) ----
    @reactive.calc
    def time_filtered_articles():
        df = enriched_articles_state.get()
        if df is None or df.empty:
            return pd.DataFrame()
        hours = input.time_hours()
        filtered = filter_by_time(df, hours)
        if filtered is None or filtered.empty:
            return pd.DataFrame()
        return filtered

    # ---- Filter flow: time + sentiment on cached data only ----
    @reactive.calc
    def filtered_articles():
        df = enriched_articles_state.get()
        if df is None or df.empty:
            logger.info("TIME_FILTER stage: enriched_articles_state is empty; returning empty DataFrame")
            return pd.DataFrame()
        hours = input.time_hours()
        # ---- Time filter diagnostics (before filtering) ----
        base_rows = len(df)
        base_sec_counts = {}
        base_sent_dist = {}
        if "section" in df.columns:
            base_sec_series = (
                df["section"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )
            base_sec_counts = base_sec_series.value_counts().to_dict()
        base_sentiment_dist = {}
        if "sentiment" in df.columns:
            base_sentiment_dist = (
                df["sentiment"]
                .astype(str)
                .str.lower()
                .str.strip()
                .replace("nan", "neutral")
                .value_counts()
                .to_dict()
            )
        logger.info(
            "TIME_FILTER stage: before_filter hours=%s rows=%s section_distribution=%s sentiment_distribution=%s",
            hours,
            base_rows,
            base_sec_counts,
            base_sentiment_dist,
        )
        filtered = filter_by_time(df, hours)
        if filtered is None or filtered.empty:
            logger.info(
                "TIME_FILTER stage: after_filter hours=%s rows=%s",
                hours,
                0 if filtered is None else len(filtered),
            )
            return pd.DataFrame()
        logger.info(
            "TIME_FILTER stage: after_filter hours=%s rows=%s",
            hours,
            len(filtered),
        )
        s = input.sentiment()
        if not s:
            # No sentiment filter applied — show all
            if "sentiment" not in filtered.columns:
                filtered = filtered.copy()
                filtered["sentiment"] = "neutral"
            logger.info("SENTIMENT_FILTER stage: no filter applied; rows=%s", len(filtered))
            return filtered
        # Filter by sentiment (sidebar toggle)
        if "sentiment" not in filtered.columns:
            filtered = filtered.copy()
            filtered["sentiment"] = "neutral"
        if isinstance(s, str):
            sel = (s.lower().strip(),)
        else:
            sel = tuple(str(x).lower().strip() for x in s)
        if not sel:
            return filtered
        sent_col = filtered["sentiment"].astype(str).str.lower().str.strip().replace("nan", "neutral")
        after = filtered[sent_col.isin(sel)].reset_index(drop=True)
        logger.info("SENTIMENT_FILTER stage: filter_values=%s rows_before=%s rows_after=%s", sel, len(filtered), len(after))
        return after

    def category_articles_for(cat: str):
        arts = filtered_articles()
        result = filter_by_category(arts, cat) if arts is not None and not arts.empty else pd.DataFrame()
        # If this category is empty (e.g. sentiment filter removed all), show time+category so the tab shows something
        if result is None or result.empty:
            time_only = time_filtered_articles()
            if time_only is not None and not time_only.empty:
                fallback = filter_by_category(time_only, cat)
                if fallback is not None and not fallback.empty:
                    logger.info("CATEGORY_FILTER stage: category=%s fallback (showing all sentiments) rows=%s", cat, len(fallback))
                    return fallback
        logger.info(
            "CATEGORY_FILTER stage: category=%s rows_before=%s rows_after=%s",
            cat,
            len(arts) if arts is not None else 0,
            len(result) if result is not None else 0,
        )
        return result if result is not None else pd.DataFrame()

    def current_cards_for(cat: str):
        ps = page_state.get()
        if not isinstance(ps, dict):
            ps = {}
        page = ps.get(cat, 1)
        arts = category_articles_for(cat)
        if arts is None or arts.empty:
            return pd.DataFrame()
        if page == 1:
            return select_first_six(arts)
        used = list(ps.get(f"{cat}_used", []))
        sel = select_next_six(arts, used)
        return sel if sel is not None and not sel.empty else pd.DataFrame()

    def update_page(cat: str):
        ps = page_state.get()
        if not isinstance(ps, dict):
            ps = {}
        ps = dict(ps)
        arts = category_articles_for(cat)
        if arts is None or arts.empty:
            return
        page = ps.get(cat, 1) + 1
        used = list(ps.get(f"{cat}_used", []))
        if page == 2:
            first6 = select_first_six(arts)
            if not first6.empty and "url" in first6.columns:
                used.extend(first6["url"].tolist())
        else:
            next6 = select_next_six(arts, used)
            if next6 is not None and not next6.empty and "url" in next6.columns:
                used.extend(next6["url"].tolist())
        ps[cat] = page
        ps[f"{cat}_used"] = used
        page_state.set(ps)

    @reactive.effect
    @reactive.event(input.next_all)
    def _():
        update_page("ALL")

    @reactive.effect
    @reactive.event(input.next_business)
    def _():
        update_page("business")

    @reactive.effect
    @reactive.event(input.next_arts)
    def _():
        update_page("arts")

    @reactive.effect
    @reactive.event(input.next_technology)
    def _():
        update_page("technology")

    @reactive.effect
    @reactive.event(input.next_world)
    def _():
        update_page("world")

    @reactive.effect
    @reactive.event(input.next_politics)
    def _():
        update_page("politics")

    @reactive.effect
    @reactive.event(input.time_hours, input.sentiment)
    def _reset_pagination():
        ps = page_state.get()
        if isinstance(ps, dict) and ps:
            page_state.set(dict())

    async def make_cards_ui(cat: str):
        cards = current_cards_for(cat)
        if cards is None or cards.empty:
            await _send_loading(False)
            enriched = enriched_articles_state.get()
            if enriched is None or enriched.empty:
                return ui.div(ui.p("No articles loaded. Add NYT_API_KEY to .env (project root or AppV1) and click Refresh."))
            s = input.sentiment()
            has_sentiment_filter = bool(s and (len(s) > 0 if isinstance(s, (list, tuple)) else True))
            cat_label = cat if cat != "ALL" else "articles"
            if has_sentiment_filter:
                return ui.div(ui.p(f"No {cat_label} match the selected sentiment. Clear the sentiment filter (leave all unchecked) above to see all news here."))
            return ui.div(ui.p(f"No {cat_label} in this time range. Try the ALL tab or increase the time slider (e.g. 60 hrs)."))
        tone = input.tone()
        placeholder = "placeholder.svg"
        card_list = []
        to_fetch = []
        to_fetch_indices = []
        for i in range(len(cards)):
            row = cards.iloc[i]
            url = row.get("url")
            if url is None or (isinstance(url, float) and pd.isna(url)):
                continue
            key = f"{url}|{tone}"
            if key not in summary_cache:
                title = row.get("title", "")
                abstract = row.get("abstract", "")
                sub = row.get("subtitle")
                sub = None if (sub is None or (isinstance(sub, float) and pd.isna(sub))) else sub
                to_fetch.append((str(title), str(abstract), str(sub) if sub else None))
                to_fetch_indices.append(i)
        if to_fetch:
            summaries = get_summaries_parallel(to_fetch, tone, OPENAI_API_KEY)
            for idx, summ in zip(to_fetch_indices, summaries):
                row = cards.iloc[idx]
                url = row.get("url")
                if url is not None:
                    key = f"{url}|{tone}"
                    summary_cache[key] = summ
        ps = page_state.get()
        if not isinstance(ps, dict):
            ps = {}
        page = ps.get(cat, 1)
        for i in range(len(cards)):
            row = cards.iloc[i]
            img_url = get_image_url(row, placeholder)
            url = row.get("url", "")
            key = f"{url}|{tone}"
            summ = summary_cache.get(key, str(row.get("abstract", "")))
            title = str(row.get("title", ""))
            is_breaking = (page == 1 and i in (0, 1))
            is_trending = (page == 1 and i in (2, 3))
            card_list.append(news_card_ui(f"card_{i}", title, img_url, summ, str(url), is_breaking, is_trending))
        await _send_loading(False)
        return ui.div(*card_list, class_="news-cards-grid")

    @render.ui
    async def news_all():
        return await make_cards_ui("ALL")

    @render.ui
    async def news_business():
        return await make_cards_ui("business")

    @render.ui
    async def news_arts():
        return await make_cards_ui("arts")

    @render.ui
    async def news_technology():
        return await make_cards_ui("technology")

    @render.ui
    async def news_world():
        return await make_cards_ui("world")

    @render.ui
    async def news_politics():
        return await make_cards_ui("politics")


app = App(app_ui, server, static_assets=Path(__file__).parent / "www")

if __name__ == "__main__":
    from shiny import run_app
    run_app(app, launch_browser=True)
