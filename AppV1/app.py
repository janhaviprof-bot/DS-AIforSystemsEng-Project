# News for People in Hurry - Shiny for Python (merged: app_update UI + app.py backend)
# Run: shiny run app_merged.py

from pathlib import Path
import asyncio
import logging
import os
from datetime import datetime

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
import json
import pandas as pd

from config import NYT_API_KEY, OPENAI_API_KEY, NYT_SECTIONS
from ui.layout import app_header, sidebar_children, empty_state_message
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
from research_agent import run_research_brief

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
<p style="color:#57534e;font-size:0.9rem;">Loading your news…</p>
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

# UI (from app_update: card-based sidebar, feed stats, layout)
app_ui = ui.page_fluid(
    ui.HTML(f'<div id="static-loading-wrap" style="position:fixed;inset:0;z-index:9999;">{LOADING_HTML}</div>'),
    ui.head_content(ui.include_css(Path(__file__).parent / "www" / "styles.css")),
    ui.tags.head(
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
        app_header(),
        ui.layout_sidebar(
            ui.sidebar(
                *sidebar_children(),
                title="Filters",
                width=350,
                open={"desktop": "open", "mobile": "closed"},
            ),
            ui.div(
                ui.navset_tab(
                    ui.nav_panel(
                        "All",
                        ui.output_ui("news_all"),
                        ui.div(
                            ui.div(ui.output_ui("page_ctx_all"), class_="pagination-context"),
                            ui.div(
                                ui.input_action_button("prev_all", "Previous page", class_="btn-secondary"),
                                ui.input_action_button("next_all", "Next page", class_="btn-primary"),
                                class_="pagination-buttons",
                            ),
                            class_="pagination-bar",
                        ),
                        value="ALL",
                    ),
                    ui.nav_panel(
                        "Business",
                        ui.output_ui("news_business"),
                        ui.div(
                            ui.div(ui.output_ui("page_ctx_business"), class_="pagination-context"),
                            ui.div(
                                ui.input_action_button("prev_business", "Previous page", class_="btn-secondary"),
                                ui.input_action_button("next_business", "Next page", class_="btn-primary"),
                                class_="pagination-buttons",
                            ),
                            class_="pagination-bar",
                        ),
                        value="business",
                    ),
                    ui.nav_panel(
                        "Arts",
                        ui.output_ui("news_arts"),
                        ui.div(
                            ui.div(ui.output_ui("page_ctx_arts"), class_="pagination-context"),
                            ui.div(
                                ui.input_action_button("prev_arts", "Previous page", class_="btn-secondary"),
                                ui.input_action_button("next_arts", "Next page", class_="btn-primary"),
                                class_="pagination-buttons",
                            ),
                            class_="pagination-bar",
                        ),
                        value="arts",
                    ),
                    ui.nav_panel(
                        "Technology",
                        ui.output_ui("news_technology"),
                        ui.div(
                            ui.div(ui.output_ui("page_ctx_technology"), class_="pagination-context"),
                            ui.div(
                                ui.input_action_button("prev_technology", "Previous page", class_="btn-secondary"),
                                ui.input_action_button("next_technology", "Next page", class_="btn-primary"),
                                class_="pagination-buttons",
                            ),
                            class_="pagination-bar",
                        ),
                        value="technology",
                    ),
                    ui.nav_panel(
                        "World",
                        ui.output_ui("news_world"),
                        ui.div(
                            ui.div(ui.output_ui("page_ctx_world"), class_="pagination-context"),
                            ui.div(
                                ui.input_action_button("prev_world", "Previous page", class_="btn-secondary"),
                                ui.input_action_button("next_world", "Next page", class_="btn-primary"),
                                class_="pagination-buttons",
                            ),
                            class_="pagination-bar",
                        ),
                        value="world",
                    ),
                    ui.nav_panel(
                        "Politics",
                        ui.output_ui("news_politics"),
                        ui.div(
                            ui.div(ui.output_ui("page_ctx_politics"), class_="pagination-context"),
                            ui.div(
                                ui.input_action_button("prev_politics", "Previous page", class_="btn-secondary"),
                                ui.input_action_button("next_politics", "Next page", class_="btn-primary"),
                                class_="pagination-buttons",
                            ),
                            class_="pagination-bar",
                        ),
                        value="politics",
                    ),
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
    _log_openai_key_once()
    sentiment_cache: dict = {}
    summary_cache: dict = {}
    page_state = reactive.value(dict())
    is_loading = reactive.value(False)
    initial_load_done = reactive.value(False)
    last_refresh = reactive.value(None)
    # Enriched articles (with sentiment + impact_label) — updated only on refresh
    enriched_articles_state = reactive.value(pd.DataFrame())
    # Research brief modal (OpenAI tool-calling agent)
    research_brief_state = reactive.value({"phase": "idle", "text": ""})

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
            last_refresh.set(datetime.now())
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
        base_rows = len(df)
        base_sec_counts = {}
        base_sentiment_dist = {}
        if "section" in df.columns:
            base_sec_series = (
                df["section"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )
            base_sec_counts = base_sec_series.value_counts().to_dict()
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
            logger.info("TIME_FILTER stage: after_filter hours=%s rows=%s", hours, 0 if filtered is None else len(filtered))
            return pd.DataFrame()
        logger.info("TIME_FILTER stage: after_filter hours=%s rows=%s", hours, len(filtered))
        s = input.sentiment()
        if not s:
            if "sentiment" not in filtered.columns:
                filtered = filtered.copy()
                filtered["sentiment"] = "neutral"
            logger.info("SENTIMENT_FILTER stage: no filter applied; rows=%s", len(filtered))
            return filtered
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
        result = filter_by_category(arts, cat) if arts is not None and not arts.empty else pd.DataFrame()
        # Category fallback: if sentiment filter removed all, show time+category
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
        current_page = ps.get(cat, 1)
        used = list(ps.get(f"{cat}_used", []))
        if current_page == 1:
            first_batch = select_first_six(arts)
            if first_batch.empty or "url" not in first_batch.columns:
                return
            used = list(first_batch["url"].tolist())
            if select_next_six(arts, used).empty:
                return
        else:
            next_batch = select_next_six(arts, used)
            if next_batch is None or next_batch.empty or "url" not in next_batch.columns:
                return
            used.extend(next_batch["url"].tolist())
        ps[cat] = current_page + 1
        ps[f"{cat}_used"] = used
        page_state.set(ps)

    def update_page_prev(cat: str):
        ps = page_state.get()
        if not isinstance(ps, dict):
            ps = {}
        ps = dict(ps)
        page = ps.get(cat, 1)
        if page <= 1:
            return
        ps = dict(ps)
        ps[cat] = page - 1
        if ps[cat] == 1:
            ps[f"{cat}_used"] = []
        page_state.set(ps)

    @reactive.effect
    @reactive.event(input.prev_all)
    def _():
        update_page_prev("ALL")

    @reactive.effect
    @reactive.event(input.next_all)
    def _():
        update_page("ALL")

    @reactive.effect
    @reactive.event(input.prev_business)
    def _():
        update_page_prev("business")

    @reactive.effect
    @reactive.event(input.next_business)
    def _():
        update_page("business")

    @reactive.effect
    @reactive.event(input.prev_arts)
    def _():
        update_page_prev("arts")

    @reactive.effect
    @reactive.event(input.next_arts)
    def _():
        update_page("arts")

    @reactive.effect
    @reactive.event(input.prev_technology)
    def _():
        update_page_prev("technology")

    @reactive.effect
    @reactive.event(input.next_technology)
    def _():
        update_page("technology")

    @reactive.effect
    @reactive.event(input.prev_world)
    def _():
        update_page_prev("world")

    @reactive.effect
    @reactive.event(input.next_world)
    def _():
        update_page("world")

    @reactive.effect
    @reactive.event(input.prev_politics)
    def _():
        update_page_prev("politics")

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

    def _page_context(cat: str) -> str:
        arts = category_articles_for(cat)
        if arts is None or arts.empty:
            return "No articles"
        ps = page_state.get()
        if not isinstance(ps, dict):
            ps = {}
        page = ps.get(cat, 1)
        total = len(arts)
        if total == 0:
            return "No articles"
        start_idx = (page - 1) * 6
        # Clamp to valid range: if current page is past last page, show last page's range
        if start_idx >= total:
            last_page_start = ((total - 1) // 6) * 6
            start_idx = last_page_start
        end_idx = min(start_idx + 6, total)
        return f"{start_idx + 1}–{end_idx} of {total}"

    @render.ui
    def page_ctx_all():
        return ui.span(_page_context("ALL"))

    @render.ui
    def page_ctx_business():
        return ui.span(_page_context("business"))

    @render.ui
    def page_ctx_arts():
        return ui.span(_page_context("arts"))

    @render.ui
    def page_ctx_technology():
        return ui.span(_page_context("technology"))

    @render.ui
    def page_ctx_world():
        return ui.span(_page_context("world"))

    @render.ui
    def page_ctx_politics():
        return ui.span(_page_context("politics"))

    @reactive.calc
    def research_article_choices():
        tab = input.category_tabs()
        cat = str(tab).strip() if tab else "ALL"
        if cat not in ("ALL", "business", "arts", "technology", "world", "politics"):
            cat = "ALL"
        cards = current_cards_for(cat)
        if cards is None or cards.empty:
            return {}
        out: dict[str, str] = {}
        for _, row in cards.iterrows():
            u = row.get("url")
            if u is None or (isinstance(u, float) and pd.isna(u)):
                continue
            t = str(row.get("title", "")) or "(no title)"
            label = (t[:72] + "…") if len(t) > 72 else t
            out[str(u)] = label
        return out

    @reactive.effect
    def _research_select_sync():
        input.category_tabs()
        page_state.get()
        filtered_articles()
        ch = research_article_choices()
        sel = list(ch.keys())[0] if ch else None
        ui.update_select("research_article_url", choices=ch, selected=sel, session=session)

    def _row_for_article_url(url: str) -> pd.Series | None:
        df = enriched_articles_state.get()
        if df is None or df.empty or not url:
            return None
        mask = df["url"].astype(str) == str(url)
        sub = df.loc[mask]
        if sub.empty:
            return None
        return sub.iloc[0]

    def _research_modal():
        return ui.modal(
            ui.output_ui("research_modal_body"),
            title="Research brief",
            easy_close=True,
            footer=ui.modal_button("Close"),
            size="lg",
        )

    @render.ui
    def research_modal_body():
        st = research_brief_state()
        phase = st.get("phase", "idle")
        text = st.get("text", "")
        if phase == "loading":
            return ui.div(
                ui.p("Generating research brief…"),
                ui.p(
                    "Calling OpenAI with Wikipedia and Yahoo Finance tools as needed.",
                    class_="stats-hint",
                ),
                class_="research-loading",
            )
        if phase == "error":
            return ui.div(ui.p(text, class_="research-error"), class_="research-modal-inner")
        if phase == "done":
            return ui.div(ui.pre(text, class_="research-brief-pre"), class_="research-modal-inner")
        return ui.div(ui.p("—"), class_="research-modal-inner")

    @reactive.effect
    @reactive.event(input.research_generate)
    async def _research_generate():
        ch = research_article_choices()
        url = input.research_article_url()
        if not ch or not url or str(url) not in ch:
            research_brief_state.set(
                {"phase": "error", "text": "No article selected, or the list is empty. Load news and pick a story."}
            )
            ui.modal_show(_research_modal())
            return
        if not OPENAI_API_KEY or not str(OPENAI_API_KEY).strip():
            research_brief_state.set(
                {
                    "phase": "error",
                    "text": "OPENAI_API_KEY is not set. Add it to your .env file (see SETUP_ENV.md).",
                }
            )
            ui.modal_show(_research_modal())
            return
        row = _row_for_article_url(str(url))
        if row is None:
            research_brief_state.set(
                {
                    "phase": "error",
                    "text": "That article is no longer in the current feed. Refresh news and try again.",
                }
            )
            ui.modal_show(_research_modal())
            return

        research_brief_state.set({"phase": "loading", "text": ""})
        ui.modal_show(_research_modal())

        title = str(row.get("title", "") or "")
        abstract = str(row.get("abstract", "") or "")
        if abstract in ("", "nan"):
            abstract = ""
        sub = row.get("subtitle")
        if sub is None or (isinstance(sub, float) and pd.isna(sub)):
            sub_s = ""
        else:
            sub_s = str(sub)
        sec = row.get("section")
        if sec is None or (isinstance(sec, float) and pd.isna(sec)):
            sec = row.get("fetched_from_section")
        if sec is None or (isinstance(sec, float) and pd.isna(sec)):
            sec_s = ""
        else:
            sec_s = str(sec)
        try:
            brief = await asyncio.to_thread(
                run_research_brief,
                title=title,
                abstract=abstract,
                subtitle=sub_s,
                section=sec_s,
                article_url=str(url),
                api_key=OPENAI_API_KEY,
            )
            research_brief_state.set({"phase": "done", "text": brief})
        except Exception as e:
            logger.exception("Research brief failed: %s", e)
            research_brief_state.set({"phase": "error", "text": str(e)})

    async def make_cards_ui(cat: str):
        cards = current_cards_for(cat)
        if cards is None or cards.empty:
            await _send_loading(False)
            enriched = enriched_articles_state.get()
            if enriched is None or enriched.empty:
                return empty_state_message(no_articles_loaded=True)
            s = input.sentiment()
            has_sentiment_filter = bool(s and (len(s) > 0 if isinstance(s, (list, tuple)) else True))
            cat_label = cat if cat != "ALL" else "articles"
            return empty_state_message(
                no_articles_loaded=False,
                sentiment_filter_active=has_sentiment_filter,
                category_label=cat_label,
            )
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
            # Badges by slot position on page 1 only: 0-1 = BREAKING, 2-3 = TRENDING
            is_breaking = (page == 1 and i in (0, 1))
            is_trending = (page == 1 and i in (2, 3))
            sec = row.get("section") or row.get("fetched_from_section")
            section_str = str(sec).strip() if sec is not None and not (isinstance(sec, float) and pd.isna(sec)) else None
            pub = row.get("published_date")
            if pub is not None and not (isinstance(pub, float) and pd.isna(pub)):
                try:
                    published_date_str = pub.strftime("%b %d, %H:%M") if hasattr(pub, "strftime") else str(pub)[:16]
                except Exception:
                    published_date_str = None
            else:
                published_date_str = None
            card_list.append(
                news_card_ui(
                    f"card_{i}",
                    title,
                    img_url,
                    summ,
                    str(url),
                    is_breaking,
                    is_trending,
                    section=section_str,
                    published_date=published_date_str,
                )
            )
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
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
