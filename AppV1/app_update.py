# News for People in Hurry - Shiny for Python (refactored for stability)
# Run: shiny run app.py

from pathlib import Path
import logging
from datetime import datetime

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
from modules.news_cards import get_image_url, news_card_ui

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from data.fun_facts import FUN_FACTS
except ImportError:
    FUN_FACTS = ["Loading your news…"]

CATEGORIES = ["ALL", "business", "sports", "arts", "technology", "world", "politics"]

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
            /* Page layout & spacing */
            .main-container { max-width: 1400px; margin: 0 auto; padding: 1.5rem 2rem 3rem; }
            .app-header { background: linear-gradient(135deg, #A61E1E 0%, #8B1A1A 100%); color: white;
                padding: 1.5rem 2rem; margin: 0 0 1.5rem 0; border-radius: 12px;
                box-shadow: 0 4px 12px rgba(166,30,30,0.2); }
            .app-header h1 { margin: 0; font-size: 1.75rem; font-weight: 600; letter-spacing: -0.02em; }
            .app-header .subtitle { margin: 0.35rem 0 0; font-size: 0.95rem; opacity: 0.9; }
            /* Sidebar control cards */
            .control-card { margin-bottom: 1rem; border-radius: 10px; overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #eee; }
            .control-card .btn { width: 100%; }
            .control-card .card-header { background: #f8f9fa; font-weight: 600; font-size: 0.9rem;
                padding: 0.6rem 1rem; border-bottom: 1px solid #eee; }
            /* Stats card */
            .stats-card .card-body { padding: 1.25rem; min-height: 280px; }
            .stats-content { font-size: 0.9rem; padding: 0.25rem 0; }
            .stat-row { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem; }
            .stat-row:last-child { margin-bottom: 0; }
            .stat-row-double { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
            .stat-row-double > div { display: flex; align-items: center; gap: 0.4rem; }
            .stat-icon { font-size: 1.25rem; line-height: 1; }
            .stat-value { font-weight: 700; font-size: 1.1rem; color: #333; }
            .stat-value.stat-small { font-size: 0.9rem; font-weight: 600; }
            .stat-value.stat-breaking { color: #c0392b; }
            .stat-value.stat-trending { color: #2980b9; }
            .stat-label { color: #666; font-size: 0.85rem; }
            .stat-sentiment { font-size: 0.95rem; }
            .stats-divider { height: 1px; background: #eee; margin: 0.6rem 0; }
            .stats-empty { margin: 0; color: #666; }
            .stats-hint { margin: 0.5rem 0 0; font-size: 0.85rem; color: #888; }
            .control-card .card-body { padding: 1rem; }
            /* News cards */
            .news-card { border: 1px solid #e0e0e0; border-radius: 10px; margin-bottom: 16px; overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; flex-direction: column;
                transition: box-shadow 0.2s ease; }
            .news-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
            .news-card .card-badge-area { min-height: 24px; padding: 4px 12px; }
            .news-card .card-badge-area .badge-placeholder { visibility: hidden; font-size: 0.75em; }
            .news-card .card-image { width: 100%; height: 180px; object-fit: cover; }
            .news-card .card-body { padding: 14px; flex: 1; display: flex; flex-direction: column; }
            .news-card .card-title { margin: 0 0 8px 0; font-size: 1.1em; }
            .news-card .card-summary { font-size: 0.9em; color: #555; margin-bottom: 8px; line-height: 1.45; flex: 1; }
            .news-card .card-link-wrap { text-align: right; margin-top: auto; }
            .news-card .card-link { color: #0066cc; text-decoration: none; font-weight: 500; }
            .news-card .card-link:hover { text-decoration: underline; }
            .badge-breaking { background: #c0392b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; }
            .badge-trending { background: #2980b9; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; }
            .news-cards-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; padding: 0.5rem 0; }
            /* Content area card */
            .content-card { border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
                border: 1px solid #eee; background: #fff; }
            .content-card .nav-tabs { padding: 0 1rem; background: #f8f9fa; border-bottom: 1px solid #eee; }
            .content-card .tab-content { padding: 1.25rem; min-height: 400px; }
            /* Loading overlay */
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
    ui.div(
        ui.div(
            ui.h1("News for People in Hurry"),
            ui.p("Stay informed with curated headlines from The New York Times", class_="subtitle"),
            class_="app-header",
        ),
        ui.layout_sidebar(
            ui.sidebar(
                ui.card(
                    ui.card_header("⏱ Time range"),
                    ui.input_slider("time_hours", "Articles from the last (6–48 hrs, default 24)", 6, 48, value=24, step=1),
                    class_="control-card",
                ),
                ui.card(
                    ui.card_header("Sentiment"),
                    ui.input_checkbox_group(
                        "sentiment",
                        "Filter by classification (default: show all)",
                        choices=["positive", "negative", "neutral"],
                        inline=True,
                    ),
                    class_="control-card",
                ),
                ui.card(
                    ui.card_header("Summary style"),
                    ui.input_select(
                        "tone",
                        "Classify tone",
                        choices=["Informational", "Opinion", "Analytical"],
                        selected="Informational",
                    ),
                    class_="control-card",
                ),
                ui.card(
                    ui.input_action_button("refresh", "Refresh News", class_="btn-primary"),
                    class_="control-card",
                ),
                ui.card(
                    ui.card_header("📊 Feed stats"),
                    ui.output_ui("sidebar_stats"),
                    class_="control-card stats-card",
                ),
                title="Filters",
                width=350,
                open="always",
            ),
            ui.div(
                ui.navset_tab(
                    ui.nav_panel("ALL", ui.output_ui("news_all"), ui.input_action_button("next_all", "Next")),
                    ui.nav_panel("business", ui.output_ui("news_business"), ui.input_action_button("next_business", "Next")),
                    ui.nav_panel("sports", ui.output_ui("news_sports"), ui.input_action_button("next_sports", "Next")),
                    ui.nav_panel("arts", ui.output_ui("news_arts"), ui.input_action_button("next_arts", "Next")),
                    ui.nav_panel("technology", ui.output_ui("news_technology"), ui.input_action_button("next_technology", "Next")),
                    ui.nav_panel("world", ui.output_ui("news_world"), ui.input_action_button("next_world", "Next")),
                    ui.nav_panel("politics", ui.output_ui("news_politics"), ui.input_action_button("next_politics", "Next")),
                    id="category_tabs",
                    selected="ALL",
                ),
                class_="content-card",
            ),
        ),
        class_="main-container",
    ),
)


def server(input: Inputs, output: Outputs, session: Session):
    sentiment_cache: dict = {}
    summary_cache: dict = {}
    page_state = reactive.value(dict())
    is_loading = reactive.value(False)
    initial_load_done = reactive.value(False)
    last_refresh = reactive.value(None)
    # Enriched articles (with sentiment) — updated only on refresh; never None
    enriched_articles_state = reactive.value(pd.DataFrame())

    def _run_refresh():
        # Clear sentiment cache each refresh to avoid stale labels
        sentiment_cache.clear()
        if is_loading.get():
            return
        is_loading.set(True)
        session.send_custom_message("show_loading", {})
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
            logger.info("Fetched %s raw articles from NYT", len(raw))
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
            # Debug visibility for sentiment pipeline
            print("Sentiment distribution:", arts["sentiment"].value_counts().to_dict())
            print("OPENAI KEY PRESENT?", bool(OPENAI_API_KEY))
            logger.info("Sentiment distribution: %s", arts["sentiment"].value_counts().to_dict())
            enriched_articles_state.set(arts)
            logger.info("Enriched and stored %s articles", len(arts))
        except Exception as e:
            logger.exception("Refresh failed: %s", e)
            enriched_articles_state.set(pd.DataFrame())
        finally:
            is_loading.set(False)
            last_refresh.set(datetime.now())
            session.send_custom_message("hide_loading", {})

    # ---- Refresh flow: on button click ----
    @reactive.effect
    @reactive.event(input.refresh)
    def _refresh_flow():
        _run_refresh()

    # ---- Initial load: run once when dashboard first opens ----
    @reactive.effect
    def _initial_load():
        if initial_load_done.get():
            return
        initial_load_done.set(True)
        _run_refresh()

    # ---- Filter flow: time + sentiment on cached data only ----
    @reactive.calc
    def filtered_articles():
        df = enriched_articles_state.get()
        if df is None or df.empty:
            return pd.DataFrame()
        hours = input.time_hours()
        filtered = filter_by_time(df, hours)
        if filtered is None or filtered.empty:
            return pd.DataFrame()
        s = input.sentiment()
        if not s:
            # No sentiment filter applied
            if "sentiment" not in filtered.columns:
                filtered = filtered.copy()
                filtered["sentiment"] = "neutral"
            return filtered
        # Ensure sentiment column exists before filtering
        if "sentiment" not in filtered.columns:
            filtered = filtered.copy()
            filtered["sentiment"] = "neutral"
        # Normalize selection: tuple of lowercase, stripped labels
        if isinstance(s, str):
            sel = (s.lower().strip(),)
        else:
            sel = tuple(str(x).lower().strip() for x in s)
        if not sel:
            return filtered
        # Normalize sentiment column: lowercase, treat NaN as "neutral", for reliable match
        sent = filtered["sentiment"].astype(str).str.lower().str.strip().replace("nan", "neutral")
        return filtered[sent.isin(sel)].reset_index(drop=True)

    @render.ui
    def sidebar_stats():
        arts = filtered_articles()
        refreshed = last_refresh.get()
        if arts is None or arts.empty:
            msg = "No articles yet."
            if refreshed:
                msg += " Try increasing the time range or changing filters."
            children = [ui.p(msg, class_="stats-empty")]
            if not refreshed:
                children.append(ui.p("Click Refresh News to load articles.", class_="stats-hint"))
            return ui.div(*children, class_="stats-content")
        total = len(arts)
        breaking = int(arts["is_breaking"].sum()) if "is_breaking" in arts.columns else 0
        trending = int(arts["is_trending"].sum()) if "is_trending" in arts.columns else 0
        sent = arts["sentiment"].value_counts() if "sentiment" in arts.columns else pd.Series(dtype=int)
        pos = int(sent.get("positive", 0))
        neg = int(sent.get("negative", 0))
        neu = int(sent.get("neutral", 0))
        # US vs International: world section = international, others = US
        sec_col = arts.get("section", pd.Series([""] * len(arts)))
        fetched_col = arts.get("fetched_from_section", pd.Series([""] * len(arts)))
        sec_str = sec_col.fillna("").astype(str).str.lower()
        fetched_str = fetched_col.fillna("").astype(str).str.lower()
        is_world = (sec_str == "world") | (fetched_str == "world")
        n_intl = int(is_world.sum())
        n_us = total - n_intl
        refresh_str = refreshed.strftime("%I:%M %p") if refreshed else "—"
        return ui.div(
            ui.div(
                ui.span("📰", class_="stat-icon"),
                ui.span(str(total), class_="stat-value"),
                ui.span("articles", class_="stat-label"),
                class_="stat-row",
            ),
            ui.div(
                ui.div(
                    ui.span("🔥", class_="stat-icon"),
                    ui.span(str(breaking), class_="stat-value stat-breaking"),
                    ui.span("breaking", class_="stat-label"),
                ),
                ui.div(
                    ui.span("📈", class_="stat-icon"),
                    ui.span(str(trending), class_="stat-value stat-trending"),
                    ui.span("trending", class_="stat-label"),
                ),
                class_="stat-row stat-row-double",
            ),
            ui.div(
                ui.span("💭", class_="stat-icon"),
                ui.span("Sentiment:", class_="stat-label"),
                ui.span(f"⊕{pos} ⊖{neg} ○{neu}", class_="stat-sentiment"),
                class_="stat-row",
            ),
            ui.div(class_="stats-divider"),
            ui.div(
                ui.span("🌎", class_="stat-icon"),
                ui.span("Geography", class_="stat-label"),
                class_="stat-row",
            ),
            ui.div(
                ui.div(
                    ui.span(str(n_us), class_="stat-value"),
                    ui.span("US", class_="stat-label"),
                ),
                ui.div(
                    ui.span("🌍", class_="stat-icon"),
                    ui.span(str(n_intl), class_="stat-value"),
                    ui.span("International", class_="stat-label"),
                ),
                class_="stat-row stat-row-double",
            ),
            ui.div(class_="stats-divider"),
            ui.div(
                ui.span("🕐", class_="stat-icon"),
                ui.span("Last refresh:", class_="stat-label"),
                ui.span(refresh_str, class_="stat-value stat-small"),
                class_="stat-row",
            ),
            class_="stats-content",
        )

    def category_articles_for(cat: str):
        arts = filtered_articles()
        if arts is None or arts.empty:
            return pd.DataFrame()
        return filter_by_category(arts, cat)

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
    @reactive.event(input.next_sports)
    def _():
        update_page("sports")

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

    def make_cards_ui(cat: str):
        cards = current_cards_for(cat)
        if cards is None or cards.empty:
            session.send_custom_message("hide_loading", {})
            enriched = enriched_articles_state.get()
            if enriched is None or enriched.empty:
                return ui.div(ui.p("No articles found. Add NYT_API_KEY to .env (project root or AppV1 folder) and click Refresh, or check the console for errors."))
            s = input.sentiment()
            has_sentiment_filter = bool(s and (len(s) > 0 if isinstance(s, (list, tuple)) else True))
            if has_sentiment_filter:
                return ui.div(ui.p("No articles match the selected sentiment. Most articles may be classified as neutral. Add OPENAI_API_KEY to .env and click Refresh to enable AI sentiment, or try selecting 'neutral'."))
            return ui.div(ui.p("No articles in this category or time range. Try increasing the time slider (e.g. 48 hrs), switching to the ALL tab, or changing the sentiment filter."))
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
            is_breaking = bool(row.get("is_breaking", False))
            is_trending = bool(row.get("is_trending", False))
            card_list.append(news_card_ui(f"card_{i}", title, img_url, summ, str(url), is_breaking, is_trending))
        session.send_custom_message("hide_loading", {})
        return ui.div(*card_list, class_="news-cards-grid")

    @render.ui
    def news_all():
        return make_cards_ui("ALL")

    @render.ui
    def news_business():
        return make_cards_ui("business")

    @render.ui
    def news_sports():
        return make_cards_ui("sports")

    @render.ui
    def news_arts():
        return make_cards_ui("arts")

    @render.ui
    def news_technology():
        return make_cards_ui("technology")

    @render.ui
    def news_world():
        return make_cards_ui("world")

    @render.ui
    def news_politics():
        return make_cards_ui("politics")


app = App(app_ui, server, static_assets=Path(__file__).parent / "www")

if __name__ == "__main__":
    from shiny import run_app
    run_app(app, launch_browser=True)
