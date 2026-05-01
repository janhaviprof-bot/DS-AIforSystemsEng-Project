# News for People in Hurry - Shiny for Python (merged: app_update UI + app.py backend)
# Run: shiny run app_merged.py

from pathlib import Path
import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime

logging.getLogger("httpx").setLevel(logging.WARNING)

from shiny import App, Inputs, Outputs, Session, reactive, render, run_app, ui
import json
import pandas as pd

from config import NYT_API_KEY, OPENAI_API_KEY, NYT_SECTIONS
from agents.workflow import SECTION_LABELS, WORKFLOW_SECTIONS, generate_section_briefs, run_multi_agent_workflow
from agents.output_qc import compare_quick_and_full
from reporting.qc_pdf_report import generate_qc_report_pdf, qc_report_filename
from ui.layout import app_header_with_marquee, sidebar_children, empty_state_message, feature_header
from ui.agent_views import agent_marquee_ui, agent_workflow_ui, section_brief_ui
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

# region agent log
def _dbglog(hypothesis_id: str, location: str, message: str, data: dict, run_id: str = "initial"):
    try:
        payload = {
            "sessionId": "293bfe",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open("debug-293bfe.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
    except Exception:
        pass
# endregion

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
            // #region agent log
            function __emitInsightDebug(hypothesisId, message, extra) {
                try {
                    var wrap = document.querySelector('.app-header-insight-wrap');
                    var marquee = document.getElementById('agent_marquee');
                    var target = marquee || wrap || document.body;
                    var cs = window.getComputedStyle(target);
                    var wrapCs = wrap ? window.getComputedStyle(wrap) : null;
                    var payload = {
                        hypothesisId: String(hypothesisId || 'H0'),
                        message: String(message || ''),
                        wrapClass: wrap ? wrap.className : '',
                        wrapAriaBusy: wrap ? wrap.getAttribute('aria-busy') : null,
                        descendantRecalcCount: wrap ? wrap.querySelectorAll('.recalculating').length : -1,
                        globalBusyCount: document.querySelectorAll('.recalculating,[aria-busy="true"]').length,
                        wrapOpacity: wrapCs ? wrapCs.opacity : '',
                        wrapFilter: wrapCs ? wrapCs.filter : '',
                        marqueeClass: marquee ? marquee.className : '',
                        marqueeAriaBusy: marquee ? marquee.getAttribute('aria-busy') : null,
                        marqueeOpacity: cs ? cs.opacity : '',
                        marqueeFilter: cs ? cs.filter : '',
                        ts: Date.now()
                    };
                    if (extra && typeof extra === 'object') {
                        Object.keys(extra).forEach(function(k){ payload[k] = extra[k]; });
                    }
                    if (window.Shiny && typeof Shiny.setInputValue === "function") {
                        Shiny.setInputValue("insight_debug_state", payload, {priority: "event"});
                    }
                } catch (e) {}
            }
            // #endregion
            // hide_loading fires after first feed publish; shiny:idle is a fallback if the message is missed.
            $(document).on("shiny:idle", function() {
                stopLoadingOverlay();
                // #region agent log
                __emitInsightDebug('H3_idle_state_not_resetting_dim', 'shiny:idle fired');
                // #endregion
            });
            Shiny.addCustomMessageHandler("hide_loading", stopLoadingOverlay);
            Shiny.addCustomMessageHandler("show_loading", restartLoadingOverlay);
            // #region agent log
            document.addEventListener('shown.bs.tab', function(e) {
                var t = e && e.target ? (e.target.getAttribute('data-value') || e.target.textContent || '') : '';
                __emitInsightDebug('H4_tab_switch_forces_rerender', 'Tab changed', {tab: String(t).trim()});
            });
            (function watchInsightBusyState(){
                var wrap = document.querySelector('.app-header-insight-wrap');
                if (!wrap || typeof MutationObserver === 'undefined') return;
                var obs = new MutationObserver(function() {
                    __emitInsightDebug('H1_parent_busy_class_persists', 'Insight wrapper mutation');
                });
                obs.observe(wrap, {attributes:true, attributeFilter:['class','aria-busy'], subtree:true});
                __emitInsightDebug('H2_css_selector_mismatch_or_override', 'Insight observer attached');
                var bodyObs = new MutationObserver(function() {
                    __emitInsightDebug('H5_ancestor_state_forces_dim', 'Body mutation affecting busy state');
                });
                bodyObs.observe(document.body, {attributes:true, attributeFilter:['class','aria-busy'], subtree:false});
                __emitInsightDebug('H5_ancestor_state_forces_dim', 'Body observer attached');
            })();
            // #endregion
            Shiny.addCustomMessageHandler("signal_progress_ping", function(message) {
                var ts = (message && message.ts) ? message.ts : Date.now();
                if (window.Shiny && typeof Shiny.setInputValue === "function") {
                    Shiny.setInputValue("signal_progress_ping", ts, {priority: "event"});
                }
            });
            Shiny.addCustomMessageHandler("signal_progress_state", function(message) {
                if (!message) return;
                var pct = Number(message.pct || 0);
                if (!Number.isFinite(pct)) pct = 0;
                pct = Math.max(0, Math.min(100, Math.round(pct)));
                var label = String(message.label || "");
                var status = String(message.status || "");
                var pctEl = document.getElementById("signal-progress-pct");
                var fillEl = document.getElementById("signal-progress-fill");
                var noteEl = document.getElementById("signal-progress-note");
                var spinEl = document.getElementById("signal-progress-spinner");
                if (pctEl) pctEl.textContent = pct + "%";
                if (fillEl) fillEl.style.width = pct + "%";
                if (noteEl && label) noteEl.textContent = label;
                if (spinEl) {
                    var hide = (pct >= 100) || (status === "error");
                    spinEl.classList.toggle("signal-progress-spinner-hidden", hide);
                }
                if (window.Shiny && typeof Shiny.setInputValue === "function") {
                    Shiny.setInputValue("signal_progress_client_ack", {
                        pct: pct,
                        label: label,
                        status: status,
                        ts: Date.now()
                    }, {priority: "event"});
                }
            });
        """),
    ),
    ui.div(
        app_header_with_marquee(ui.output_ui("agent_marquee")),
        ui.layout_sidebar(
            ui.sidebar(
                *sidebar_children(),
                title="Filters",
                width=350,
                open="closed",
            ),
            ui.div(
                ui.navset_tab(
                    ui.nav_panel(
                        "All",
                        ui.output_ui("section_brief_all"),
                        feature_header(
                            "Top stories",
                            "Main story cards for this tab. Use the cards to scan summaries and open full NYT articles.",
                        ),
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
                        ui.output_ui("section_brief_business"),
                        feature_header(
                            "Top stories",
                            "Main story cards for this tab. Use the cards to scan summaries and open full NYT articles.",
                        ),
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
                        ui.output_ui("section_brief_arts"),
                        feature_header(
                            "Top stories",
                            "Main story cards for this tab. Use the cards to scan summaries and open full NYT articles.",
                        ),
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
                        ui.output_ui("section_brief_technology"),
                        feature_header(
                            "Top stories",
                            "Main story cards for this tab. Use the cards to scan summaries and open full NYT articles.",
                        ),
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
                        ui.output_ui("section_brief_world"),
                        feature_header(
                            "Top stories",
                            "Main story cards for this tab. Use the cards to scan summaries and open full NYT articles.",
                        ),
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
                        ui.output_ui("section_brief_politics"),
                        feature_header(
                            "Top stories",
                            "Main story cards for this tab. Use the cards to scan summaries and open full NYT articles.",
                        ),
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
                    ui.nav_panel(
                        "Signal Studio",
                        ui.output_ui("agent_workflow_panel"),
                        value="agent_workflow",
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
    section_packet_cache: dict[str, list[dict]] = {}
    agent_pipeline_cache: dict[str, dict] = {}
    # True while refresh or background enrichment is running — guards concurrent work.
    _refresh_running = [False]
    _pending_enrich = reactive.value({"seq": 0})
    page_state = reactive.value(dict())
    is_loading = reactive.value(False)
    initial_load_done = reactive.value(False)
    last_refresh = reactive.value(None)
    # Enriched articles (with sentiment + impact_label) — updated only on refresh
    enriched_articles_state = reactive.value(pd.DataFrame())
    section_brief_state = reactive.value(dict())
    agent_workflow_state = reactive.value(
        {
            "status": "idle",
            "marquee_text": "Multi-agent insight will appear here after the first refresh.",
            "marquee_qc": None,
            "qc_report": None,
            "compare_quick_full": None,
            "composite_evidence_score": None,
            "workflow": {},
            "sections": [],
            "progress_pct": 0,
            "progress_label": "Waiting",
        }
    )
    agent_session_qc_metrics = reactive.value(
        {
            "full_runs": 0,
            "full_success": 0,
            "full_fail": 0,
            "timeout_count": 0,
            "fallback_agent1": 0,
            "fallback_agent2": 0,
            "fallback_agent3": 0,
            "last_error": None,
        }
    )
    agent_refresh_token = reactive.value(0)
    # Arm agent pipeline once homepage has first data paint (no Signal Studio click required).
    agent_pipeline_armed = reactive.value(False)
    first_cards_painted = reactive.value(False)
    signal_progress_tick = reactive.value(0)
    _pending_agent_full = reactive.value({"seq": 0})
    _agent_run_seq = [0]
    # Research brief modal (OpenAI tool-calling agent)
    research_brief_state = reactive.value({"phase": "idle", "text": ""})

    def _session_qc_bump_success(workflow: dict) -> None:
        m = dict(agent_session_qc_metrics.get())
        prov = (workflow or {}).get("provenance") or {}
        m["full_runs"] = int(m.get("full_runs", 0)) + 1
        m["full_success"] = int(m.get("full_success", 0)) + 1
        for agent_key, ctr_key in (
            ("agent1", "fallback_agent1"),
            ("agent2", "fallback_agent2"),
            ("agent3", "fallback_agent3"),
        ):
            if prov.get(agent_key) == "fallback":
                m[ctr_key] = int(m.get(ctr_key, 0)) + 1
        m["last_error"] = None
        agent_session_qc_metrics.set(m)

    def _session_qc_bump_timeout() -> None:
        m = dict(agent_session_qc_metrics.get())
        m["full_runs"] = int(m.get("full_runs", 0)) + 1
        m["timeout_count"] = int(m.get("timeout_count", 0)) + 1
        agent_session_qc_metrics.set(m)

    def _session_qc_bump_fail(exc: BaseException | None) -> None:
        m = dict(agent_session_qc_metrics.get())
        m["full_runs"] = int(m.get("full_runs", 0)) + 1
        m["full_fail"] = int(m.get("full_fail", 0)) + 1
        if exc is not None:
            m["last_error"] = str(exc)[:500]
        agent_session_qc_metrics.set(m)

    async def _send_signal_progress(pct: int, label: str, status: str = ""):
        out = session.send_custom_message(
            "signal_progress_state",
            {"pct": int(max(0, min(100, pct))), "label": str(label), "status": str(status)},
        )
        if asyncio.iscoroutine(out):
            await out

    @reactive.effect
    @reactive.event(input.signal_progress_client_ack)
    def _signal_progress_client_ack_logger():
        _ = input.signal_progress_client_ack()

    # region agent log
    @reactive.effect
    @reactive.event(input.insight_debug_state)
    def _insight_debug_state_logger():
        payload = input.insight_debug_state()
        if not isinstance(payload, dict):
            return
        hypothesis_id = str(payload.get("hypothesisId", "H0"))
        message = str(payload.get("message", "Insight debug"))
        _dbglog(
            hypothesis_id,
            "app.py:_insight_debug_state_logger",
            message,
            {
                "tab": payload.get("tab"),
                "wrapClass": payload.get("wrapClass"),
                "wrapAriaBusy": payload.get("wrapAriaBusy"),
                "wrapOpacity": payload.get("wrapOpacity"),
                "wrapFilter": payload.get("wrapFilter"),
                "marqueeClass": payload.get("marqueeClass"),
                "marqueeAriaBusy": payload.get("marqueeAriaBusy"),
                "marqueeOpacity": payload.get("marqueeOpacity"),
                "marqueeFilter": payload.get("marqueeFilter"),
                "descendantRecalcCount": payload.get("descendantRecalcCount"),
                "globalBusyCount": payload.get("globalBusyCount"),
                "clientTs": payload.get("ts"),
                "activeTab": input.category_tabs(),
            },
        )
    # endregion

    async def _send_loading(show: bool):
        """Call send_custom_message; await if it returns a coroutine (Shiny async)."""
        msg = "show_loading" if show else "hide_loading"
        out = session.send_custom_message(msg, {})
        if asyncio.iscoroutine(out):
            await out

    def _scoped_enrich_articles(arts: pd.DataFrame, hours: float) -> pd.DataFrame:
        """
        Run OpenAI sentiment + impact **concurrently** for articles in the time window.
        Rows outside the window stay neutral until the user widens it.
        """
        from concurrent.futures import ThreadPoolExecutor

        arts = arts.copy()
        if arts.empty or "url" not in arts.columns:
            return arts
        if "sentiment" not in arts.columns:
            arts["sentiment"] = "neutral"
        if "impact_label" not in arts.columns:
            arts["impact_label"] = "neutral"
        scoped = filter_by_time(arts, hours)
        if scoped is None or scoped.empty:
            return arts
        scoped_urls: list[str] = []
        for u in scoped["url"].tolist():
            if u is None or (isinstance(u, float) and pd.isna(u)):
                continue
            scoped_urls.append(str(u))
        if not scoped_urls:
            return arts
        url_set = set(scoped_urls)
        api_key = OPENAI_API_KEY

        def _do_sentiment():
            to_fetch = [u for u in scoped_urls if u not in sentiment_cache]
            if to_fetch and api_key and str(api_key).strip() and "title" in arts.columns:
                titles = []
                for u in to_fetch:
                    row = arts.loc[arts["url"].astype(str) == u]
                    titles.append(str(row["title"].iloc[0]) if not row.empty else "")
                results = get_sentiments_parallel(titles, api_key)
                for u, s in zip(to_fetch, results):
                    sentiment_cache[u] = s

        def _do_impact():
            sub = arts.loc[arts["url"].astype(str).isin(url_set)].reset_index(drop=True)
            if sub.empty or not api_key or not str(api_key).strip():
                return {}
            try:
                labels = get_impacts_for_articles(sub, api_key)
                return dict(zip(sub["url"].astype(str).tolist(), labels))
            except Exception as ie:
                logger.warning("Scoped impact classification failed: %s", ie)
                return {}

        with ThreadPoolExecutor(max_workers=2) as ex:
            sent_future = ex.submit(_do_sentiment)
            impact_future = ex.submit(_do_impact)
            sent_future.result()
            impact_updates = impact_future.result()

        arts["sentiment"] = [
            sentiment_cache.get(str(u), "neutral") if u is not None and not (isinstance(u, float) and pd.isna(u)) else "neutral"
            for u in arts["url"]
        ]
        if impact_updates:
            arts["impact_label"] = [
                impact_updates.get(str(u), arts["impact_label"].iloc[i]) for i, u in enumerate(arts["url"])
            ]
        logger.info("Enrichment complete: %s articles, sentiment+impact concurrent", len(arts))
        return arts

    def _normalized_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
        if df is None or df.empty or column not in df.columns:
            return {"positive": 0, "negative": 0, "neutral": 0}
        series = (
            df[column]
            .fillna("neutral")
            .astype(str)
            .str.strip()
            .str.lower()
            .replace("nan", "neutral")
        )
        counts = {str(k): int(v) for k, v in series.value_counts().to_dict().items()}
        return {
            "positive": int(counts.get("positive", 0)),
            "negative": int(counts.get("negative", 0)),
            "neutral": int(counts.get("neutral", 0)),
        }

    def _cache_key(payload) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _fallback_brief_from_packet(packet: dict) -> str:
        label = str(packet.get("label", "Section"))
        headlines = [str(h).strip() for h in list(packet.get("headlines", [])) if str(h).strip()]
        summaries = [str(s).strip() for s in list(packet.get("article_summaries", [])) if str(s).strip()]
        if not headlines and not summaries:
            return f"{label} has no articles in the current time window."
        lead = summaries[0] if summaries else (headlines[0] if headlines else "This section is updating.")
        second = summaries[1] if len(summaries) > 1 else ""
        headline_hint = headlines[0] if headlines else label
        parts = [
            f"{label} is being driven by {headline_hint.lower()}." if headline_hint else f"{label} is active right now.",
            lead,
        ]
        if second:
            parts.append(second)
        return (" ".join(p.strip() for p in parts if p and p.strip()))[:420]

    def _build_fast_workflow(section_packets: list[dict]) -> dict[str, object]:
        """Cheap, deterministic snapshot for immediate Signal Studio rendering."""
        packets = [p for p in section_packets if str(p.get("section")) in {"business", "arts", "technology", "world", "politics"}]
        mood_score = 0
        for p in packets:
            s = p.get("sentiment_counts", {}) or {}
            mood_score += int(s.get("positive", 0)) - int(s.get("negative", 0))
        if mood_score > 2:
            mood_label = "Positive"
        elif mood_score < -2:
            mood_label = "Negative"
        else:
            mood_label = "Mixed"

        top_sections = sorted(
            packets,
            key=lambda p: int((p.get("sentiment_counts", {}) or {}).get("positive", 0))
            + int((p.get("impact_counts", {}) or {}).get("negative", 0)),
            reverse=True,
        )[:3]
        section_names = [str(p.get("label", "")).strip() for p in top_sections if str(p.get("label", "")).strip()]
        section_line = ", ".join(section_names) if section_names else "multiple sections"
        first_headline = ""
        for p in packets:
            hs = list(p.get("headlines", []))
            if hs:
                first_headline = str(hs[0]).strip()
                if first_headline:
                    break

        agent1_summary = f"Early cross-section scan points to activity across {section_line}."
        if first_headline:
            agent1_summary += f" Current lead: {first_headline}."
        agent2_desc = f"Initial global mood reads {mood_label.lower()} (score {mood_score:+d}) from visible article mix."
        agent3_insight = "Market validation is loading; this quick view will upgrade automatically with live market checks."
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "agent1": {
                "cross_section_summary": agent1_summary,
                "connections": [],
            },
            "agent2": {
                "world_mood_label": mood_label,
                "world_mood_score": mood_score,
                "description": agent2_desc,
                "reasoning": [],
            },
            "agent3": {
                "market_agreement": "mixed",
                "final_insight": agent3_insight,
                "truth_checks": [],
            },
            "market_snapshot": {
                "market_bias": "Mixed",
                "avg_change": 0.0,
                "instruments": [],
            },
            "marquee_text": agent2_desc,
        }

    async def _ensure_summaries_for_articles(cards: pd.DataFrame, tone: str) -> list[str]:
        if cards is None or cards.empty:
            return []
        to_fetch = []
        fetch_indices = []
        summaries = [""] * len(cards)
        for idx in range(len(cards)):
            row = cards.iloc[idx]
            url = row.get("url")
            key = f"{url}|{tone}"
            if url is not None and key in summary_cache:
                summaries[idx] = str(summary_cache[key])
                continue
            title = row.get("title", "")
            abstract = row.get("abstract", "")
            sub = row.get("subtitle")
            subtitle = None if (sub is None or (isinstance(sub, float) and pd.isna(sub))) else str(sub)
            to_fetch.append((str(title), str(abstract), subtitle))
            fetch_indices.append(idx)
        if to_fetch:
            fetched = await asyncio.to_thread(get_summaries_parallel, to_fetch, tone, OPENAI_API_KEY)
            for idx, summary in zip(fetch_indices, fetched):
                row = cards.iloc[idx]
                url = row.get("url")
                summaries[idx] = str(summary)
                if url is not None:
                    summary_cache[f"{url}|{tone}"] = str(summary)
        for idx, summary in enumerate(summaries):
            if summary:
                continue
            abstract = cards.iloc[idx].get("abstract", "")
            summaries[idx] = str(abstract) if abstract is not None else ""
        return summaries

    async def _build_agent_section_packets(include_summaries: bool = True) -> list[dict]:
        base = time_filtered_articles()
        if base is None or base.empty:
            return []
        tone = input.tone()
        packets_key = _cache_key(
            {
                "include_summaries": bool(include_summaries),
                "tone": tone,
                "time_hours": float(input.time_hours()),
                "rows": [
                    {
                        "url": str(row.get("url", "")),
                        "sentiment": str(row.get("sentiment", "")),
                        "impact": str(row.get("impact_label", "")),
                    }
                    for _, row in base.iterrows()
                ],
            }
        )
        cached_packets = section_packet_cache.get(packets_key)
        if cached_packets is not None:
            return cached_packets

        section_cards: list[tuple[str, pd.DataFrame]] = []
        for section in WORKFLOW_SECTIONS:
            section_df = filter_by_category(base, section) if section != "ALL" else base.copy()
            cards = select_first_six(section_df)
            section_cards.append((section, cards))

        if include_summaries:
            summary_tasks = [
                _ensure_summaries_for_articles(cards, tone)
                for _, cards in section_cards
            ]
            all_summaries = await asyncio.gather(*summary_tasks)
        else:
            all_summaries = []
            for _, cards in section_cards:
                if cards is None or cards.empty:
                    all_summaries.append([])
                    continue
                # Fast path: use existing abstracts/headlines as immediate context, no LLM calls.
                abstracts = [
                    str(v).strip()
                    for v in cards.get("abstract", pd.Series(dtype=object)).fillna("").tolist()
                    if str(v).strip()
                ]
                if abstracts:
                    all_summaries.append(abstracts[:6])
                else:
                    heads = [
                        str(v).strip()
                        for v in cards.get("title", pd.Series(dtype=object)).fillna("").tolist()
                        if str(v).strip()
                    ]
                    all_summaries.append(heads[:6])

        packets = []
        for (section, cards), article_summaries in zip(section_cards, all_summaries):
            headlines = []
            urls = []
            if cards is not None and not cards.empty:
                headlines = [str(v) for v in cards.get("title", pd.Series(dtype=object)).fillna("").tolist() if str(v).strip()]
                urls = [str(v) for v in cards.get("url", pd.Series(dtype=object)).fillna("").tolist() if str(v).strip()]
            packets.append(
                {
                    "section": section,
                    "label": SECTION_LABELS.get(section, section.title()),
                    "headlines": headlines,
                    "article_summaries": article_summaries,
                    "sentiment_counts": _normalized_counts(cards, "sentiment"),
                    "impact_counts": _normalized_counts(cards, "impact_label"),
                    "urls": urls,
                }
            )
        section_packet_cache[packets_key] = packets
        return packets

    async def _run_refresh():
        """Phase 1: NYT fetch → publish placeholders → RETURN so Shiny flushes feed to browser.
        Enrichment (sentiment/impact) is scheduled via _pending_enrich for the next reactive cycle."""
        sentiment_cache.clear()
        summary_cache.clear()
        section_packet_cache.clear()
        agent_pipeline_cache.clear()
        first_cards_painted.set(False)
        if is_loading.get() or _refresh_running[0]:
            return
        _refresh_running[0] = True
        is_loading.set(True)
        await _send_loading(True)
        try:
            refresh_t0 = time.perf_counter()
            if not NYT_API_KEY or not str(NYT_API_KEY).strip():
                logger.warning("NYT_API_KEY missing; skipping fetch")
                enriched_articles_state.set(pd.DataFrame())
                _refresh_running[0] = False
                return
            fetch_t0 = time.perf_counter()
            raw = await asyncio.to_thread(fetch_nyt_articles, NYT_SECTIONS, NYT_API_KEY)
            if raw is None or raw.empty:
                logger.warning("fetch_nyt_articles returned no data (check API key and network)")
                enriched_articles_state.set(pd.DataFrame())
                _refresh_running[0] = False
                return
            logger.info("REFRESH: fetched %s raw articles", len(raw))
            if "published_date" in raw.columns:
                raw = raw.copy()
                raw["published_date"] = pd.to_datetime(raw["published_date"], utc=True, errors="coerce")
            arts = add_breaking_tag(raw)
            if arts.empty:
                enriched_articles_state.set(pd.DataFrame())
                _refresh_running[0] = False
                return
            arts = compute_trending_score(arts)
            arts = sort_latest(arts)
            if arts.empty:
                enriched_articles_state.set(pd.DataFrame())
                _refresh_running[0] = False
                return
            if "url" not in arts.columns or "title" not in arts.columns:
                enriched_articles_state.set(arts)
                _refresh_running[0] = False
                return
            arts = arts.copy()
            arts["sentiment"] = "neutral"
            arts["impact_label"] = "neutral"
            enriched_articles_state.set(arts)
            last_refresh.set(datetime.now())
            logger.info("Progressive load: published %s articles; enrichment deferred", len(arts))
            # Start Signal Studio preloading immediately after homepage first paint.
            if not agent_pipeline_armed.get():
                agent_pipeline_armed.set(True)
                agent_refresh_token.set(agent_refresh_token.get() + 1)
            _pending_enrich.set({"seq": _pending_enrich.get()["seq"] + 1, "arts": arts, "hours": float(input.time_hours())})
        except Exception as e:
            logger.exception("Refresh failed: %s", e)
            enriched_articles_state.set(pd.DataFrame())
            _refresh_running[0] = False
        finally:
            is_loading.set(False)
            await _send_loading(False)

    @reactive.effect
    @reactive.event(_pending_enrich)
    async def _run_deferred_enrichment():
        """Phase 2: runs in its own reactive cycle AFTER Shiny has flushed the feed to the browser."""
        info = _pending_enrich.get()
        arts = info.get("arts")
        hours = info.get("hours")
        if arts is None or not isinstance(arts, pd.DataFrame) or arts.empty:
            return
        try:
            enriched = await asyncio.to_thread(_scoped_enrich_articles, arts, hours)
            enriched_articles_state.set(enriched)
            # Do not re-run the agent pipeline here: it already started after phase-1 fetch.
            # A second run cleared workflow → long "Analyzing" header + redundant LLM work.
            # User can change time/tone or open Signal Studio to refresh signals.
            last_refresh.set(datetime.now())
            logger.info("Enriched and stored %s articles (background AI complete)", len(enriched))
        except Exception as ex:
            logger.exception("Deferred enrichment failed: %s", ex)
        finally:
            _refresh_running[0] = False

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

    @reactive.effect
    @reactive.event(input.time_hours)
    async def _enrich_widen_time_window():
        """When the user widens the time range, classify sentiment/impact for newly visible URLs only."""
        if _refresh_running[0] or not initial_load_done.get():
            return
        df = enriched_articles_state.get()
        if df is None or df.empty or "url" not in df.columns:
            return
        hours = float(input.time_hours())
        tw = filter_by_time(df, hours)
        if tw is None or tw.empty:
            return
        in_window = {str(u) for u in tw["url"].tolist() if u is not None and not (isinstance(u, float) and pd.isna(u))}
        need_sent = [u for u in in_window if u not in sentiment_cache]
        try:
            updated = await asyncio.to_thread(_scoped_enrich_articles, df, hours)
            enriched_articles_state.set(updated)
            if need_sent:
                logger.info("Time window widen: filled sentiment for %s newly visible URLs", len(need_sent))
        except Exception as e:
            logger.warning("Time-window incremental enrich failed: %s", e)

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
            logger.debug("TIME_FILTER: enriched_articles_state empty; returning empty DataFrame")
            return pd.DataFrame()
        hours = input.time_hours()
        if logger.isEnabledFor(logging.DEBUG):
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
            logger.debug(
                "TIME_FILTER before_filter hours=%s rows=%s section_distribution=%s sentiment_distribution=%s",
                hours,
                base_rows,
                base_sec_counts,
                base_sentiment_dist,
            )
        filtered = filter_by_time(df, hours)
        if filtered is None or filtered.empty:
            logger.debug(
                "TIME_FILTER after_filter hours=%s rows=%s",
                hours,
                0 if filtered is None else len(filtered),
            )
            return pd.DataFrame()
        logger.debug("TIME_FILTER after_filter hours=%s rows=%s", hours, len(filtered))
        s = input.sentiment()
        if not s:
            if "sentiment" not in filtered.columns:
                filtered = filtered.copy()
                filtered["sentiment"] = "neutral"
            logger.debug("SENTIMENT_FILTER: no filter applied; rows=%s", len(filtered))
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
        logger.debug("SENTIMENT_FILTER filter_values=%s rows_before=%s rows_after=%s", sel, len(filtered), len(after))
        return after

    @reactive.calc
    def category_articles_map():
        arts = filtered_articles()
        time_only = time_filtered_articles()
        out: dict[str, pd.DataFrame] = {}
        for cat in CATEGORIES:
            result = filter_by_category(arts, cat) if arts is not None and not arts.empty else pd.DataFrame()
            if (result is None or result.empty) and time_only is not None and not time_only.empty:
                fallback = filter_by_category(time_only, cat)
                if fallback is not None and not fallback.empty:
                    out[cat] = fallback
                    continue
            out[cat] = result if result is not None else pd.DataFrame()
        return out

    @reactive.calc
    def current_cards_map():
        ps = page_state.get()
        if not isinstance(ps, dict):
            ps = {}
        cat_map = category_articles_map()
        out: dict[str, pd.DataFrame] = {}
        for cat in CATEGORIES:
            arts = cat_map.get(cat, pd.DataFrame())
            if arts is None or arts.empty:
                out[cat] = pd.DataFrame()
                continue
            page = ps.get(cat, 1)
            if page == 1:
                out[cat] = select_first_six(arts)
            else:
                used = list(ps.get(f"{cat}_used", []))
                sel = select_next_six(arts, used)
                out[cat] = sel if sel is not None and not sel.empty else pd.DataFrame()
        return out

    @reactive.effect
    @reactive.event(agent_refresh_token)
    async def _run_agent_pipeline():
        if not agent_pipeline_armed.get():
            return
        logger.info("Agent pipeline triggered (run_seq=%s)", _agent_run_seq[0] + 1)
        df = time_filtered_articles()
        _agent_run_seq[0] += 1
        run_id = _agent_run_seq[0]
        if df is None or df.empty:
            section_brief_state.set(dict())
            agent_workflow_state.set(
                {
                    "status": "idle",
                    "marquee_text": "Multi-agent insight will appear here after the first refresh.",
                    "marquee_qc": None,
                    "qc_report": None,
                    "compare_quick_full": None,
                    "composite_evidence_score": None,
                    "workflow": {},
                    "sections": [],
                    "progress_pct": 0,
                    "progress_label": "Waiting",
                }
            )
            return
        prev_state = dict(agent_workflow_state.get() or {})
        prev_wf = prev_state.get("workflow") if isinstance(prev_state.get("workflow"), dict) else {}
        keep_marquee = (
            prev_state.get("status") == "ready"
            and bool(prev_wf)
            and bool(prev_wf.get("agent2") or prev_wf.get("marquee_text"))
        )
        agent_workflow_state.set(
            {
                "status": "loading",
                "marquee_text": str(
                    prev_state.get("marquee_text")
                    or "Refreshing Global Insight from the latest feed…"
                ),
                "marquee_qc": prev_state.get("marquee_qc") if keep_marquee else None,
                "qc_report": prev_state.get("qc_report") if keep_marquee else None,
                "compare_quick_full": prev_state.get("compare_quick_full") if keep_marquee else None,
                "composite_evidence_score": prev_state.get("composite_evidence_score") if keep_marquee else None,
                "workflow": prev_wf if keep_marquee else {},
                "sections": list(prev_state.get("sections") or []) if keep_marquee else [],
                "progress_pct": 20,
                "progress_label": "Building quick snapshot",
            }
        )
        await _send_signal_progress(20, "Building quick snapshot", "loading")
        try:
            packets = await _build_agent_section_packets(include_summaries=False)
            pipeline_key = _cache_key(
                {
                    "tone": input.tone(),
                    "time_hours": float(input.time_hours()),
                    "packets": packets,
                }
            )
            cached_state = agent_pipeline_cache.get(pipeline_key)
            if cached_state is not None:
                if run_id != _agent_run_seq[0]:
                    return
                section_brief_state.set(dict(cached_state.get("briefs", {})))
                wf_cached = dict(cached_state.get("workflow", {}))
                agent_workflow_state.set(
                    {
                        "status": str(cached_state.get("status", "ready")),
                        "marquee_text": str(cached_state.get("marquee_text", "")),
                        "marquee_qc": cached_state.get("marquee_qc") or wf_cached.get("marquee_qc"),
                        "qc_report": cached_state.get("qc_report") or wf_cached.get("qc_report"),
                        "compare_quick_full": cached_state.get("compare_quick_full"),
                        "composite_evidence_score": cached_state.get("composite_evidence_score")
                        or wf_cached.get("composite_evidence_score"),
                        "workflow": wf_cached,
                        "sections": list(cached_state.get("sections", [])),
                        "progress_pct": int(cached_state.get("progress_pct", 100)),
                        "progress_label": str(cached_state.get("progress_label", "Done")),
                    }
                )
                return
            # Fast first paint for All briefs + Signal Studio, then heavy LLM pipeline upgrades in background.
            quick_briefs = {str(p.get("section")): _fallback_brief_from_packet(p) for p in packets}
            quick_workflow = _build_fast_workflow(packets)
            section_brief_state.set(quick_briefs)
            agent_workflow_state.set(
                {
                    "status": "ready",
                    "marquee_text": str(quick_workflow.get("marquee_text", "Signal Studio quick view loaded.")),
                    "marquee_qc": None,
                    "qc_report": None,
                    "compare_quick_full": None,
                    "composite_evidence_score": None,
                    "workflow": quick_workflow,
                    "sections": packets,
                    "progress_pct": 60,
                    "progress_label": "Quick snapshot ready",
                }
            )
            await _send_signal_progress(60, "Quick snapshot ready", "ready")
            _pending_agent_full.set(
                {
                    "seq": _pending_agent_full.get().get("seq", 0) + 1,
                    "run_id": run_id,
                    "pipeline_key": pipeline_key,
                    "packets": packets,
                    "quick_workflow": quick_workflow,
                }
            )
        except Exception as exc:
            logger.exception("Multi-agent workflow failed: %s", exc)
            if run_id != _agent_run_seq[0]:
                return
            agent_workflow_state.set(
                {
                    "status": "error",
                    "marquee_text": "Multi-agent workflow hit a fallback path. Refresh again after checking API and network access.",
                    "marquee_qc": None,
                    "qc_report": None,
                    "compare_quick_full": None,
                    "composite_evidence_score": None,
                    "workflow": {},
                    "sections": [],
                    "progress_pct": 0,
                    "progress_label": "Retry needed",
                }
            )
            await _send_signal_progress(0, "Retry needed", "error")

    @reactive.effect
    @reactive.event(_pending_agent_full)
    async def _run_full_agent_pipeline():
        """Heavy LLM pipeline pass that upgrades the quick Signal Studio snapshot."""
        info = _pending_agent_full.get()
        packets = info.get("packets")
        run_id = int(info.get("run_id") or 0)
        pipeline_key = str(info.get("pipeline_key") or "")
        if not packets or run_id <= 0 or not pipeline_key:
            return
        async def _worker(local_info: dict):
            local_run_id = int(local_info.get("run_id") or 0)
            local_pipeline_key = str(local_info.get("pipeline_key") or "")
            try:
                full_t0 = time.perf_counter()
                current_state = dict(agent_workflow_state.get() or {})
                current_state.update({"progress_pct": 72, "progress_label": "Generating section summaries"})
                agent_workflow_state.set(current_state)
                signal_progress_tick.set(signal_progress_tick.get() + 1)
                await _send_signal_progress(72, "Generating section summaries", "ready")
                packets_with_summaries = await _build_agent_section_packets(include_summaries=True)
                current_state = dict(agent_workflow_state.get() or {})
                current_state.update({"progress_pct": 84, "progress_label": "Building section briefs"})
                agent_workflow_state.set(current_state)
                signal_progress_tick.set(signal_progress_tick.get() + 1)
                await _send_signal_progress(84, "Building section briefs", "ready")
                briefs = await asyncio.to_thread(generate_section_briefs, packets_with_summaries, OPENAI_API_KEY)
                packets_with_briefs = [{**packet, "brief": briefs.get(packet["section"], "")} for packet in packets_with_summaries]
                if local_run_id != _agent_run_seq[0]:
                    return
                current_state = dict(agent_workflow_state.get() or {})
                current_state.update({"progress_pct": 94, "progress_label": "Running multi-agent validation"})
                agent_workflow_state.set(current_state)
                signal_progress_tick.set(signal_progress_tick.get() + 1)
                await _send_signal_progress(94, "Running multi-agent validation", "ready")
                workflow = await asyncio.to_thread(run_multi_agent_workflow, packets_with_briefs, OPENAI_API_KEY)
                if local_run_id != _agent_run_seq[0]:
                    return
                section_brief_state.set(briefs)
                quick_wf = local_info.get("quick_workflow") or {}
                compare_qf = compare_quick_and_full(quick_wf if isinstance(quick_wf, dict) else {}, workflow)
                comp_score = workflow.get("composite_evidence_score")
                qc_rep = workflow.get("qc_report")
                mq = workflow.get("marquee_qc")
                agent_workflow_state.set(
                    {
                        "status": "ready",
                        "marquee_text": str(workflow.get("marquee_text", "")),
                        "marquee_qc": mq,
                        "qc_report": qc_rep,
                        "compare_quick_full": compare_qf,
                        "composite_evidence_score": comp_score,
                        "workflow": workflow,
                        "sections": packets_with_briefs,
                        "progress_pct": 100,
                        "progress_label": "Done",
                    }
                )
                signal_progress_tick.set(signal_progress_tick.get() + 1)
                await _send_signal_progress(100, "Done", "ready")
                agent_pipeline_cache[local_pipeline_key] = {
                    "status": "ready",
                    "marquee_text": str(workflow.get("marquee_text", "")),
                    "marquee_qc": mq,
                    "qc_report": qc_rep,
                    "compare_quick_full": compare_qf,
                    "composite_evidence_score": comp_score,
                    "workflow": workflow,
                    "sections": packets_with_briefs,
                    "briefs": briefs,
                    "progress_pct": 100,
                    "progress_label": "Done",
                }
                _session_qc_bump_success(workflow)
                logger.info("Agent pipeline complete (run_id=%s)", local_run_id)
            except Exception as exc:
                logger.exception("Full agent pipeline failed: %s", exc)
                if local_run_id != _agent_run_seq[0]:
                    return
                _session_qc_bump_fail(exc)

        asyncio.create_task(_worker(dict(info)))

    @reactive.effect
    @reactive.event(input.time_hours, input.tone)
    def _rerun_agent_pipeline_on_controls():
        """Keep Signal Studio reactive to controls, but only after it has been opened."""
        if not agent_pipeline_armed.get():
            return
        tab = str(input.category_tabs() or "")
        if tab != "agent_workflow":
            return
        agent_refresh_token.set(agent_refresh_token.get() + 1)

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
        return category_articles_map().get(cat, pd.DataFrame())

    def current_cards_for(cat: str):
        return current_cards_map().get(cat, pd.DataFrame())

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

    def _section_brief_output(section: str):
        briefs = section_brief_state.get()
        section_df = filter_by_category(time_filtered_articles(), section) if section != "ALL" else time_filtered_articles()
        cards = select_first_six(section_df)
        if cards is None or cards.empty:
            return ui.div()
        label = SECTION_LABELS.get(section, section.title())
        summary = ""
        if isinstance(briefs, dict):
            summary = str(briefs.get(section, ""))
        if not summary.strip():
            headlines = [str(v).strip() for v in cards.get("title", pd.Series(dtype=object)).fillna("").tolist() if str(v).strip()]
            summaries = [str(v).strip() for v in cards.get("abstract", pd.Series(dtype=object)).fillna("").tolist() if str(v).strip()]
            summary = _fallback_brief_from_packet(
                {
                    "label": label,
                    "headlines": headlines,
                    "article_summaries": summaries,
                }
            )
        return section_brief_ui(
            label,
            summary,
            _normalized_counts(cards, "sentiment"),
            help_text="Quick section summary and sentiment mix for the currently visible stories in this tab.",
        )

    @render.ui
    def agent_marquee():
        return agent_marquee_ui(agent_workflow_state.get())

    @render.download(filename=lambda: qc_report_filename())
    def qc_report_pdf():
        pdf_bytes = generate_qc_report_pdf(
            dict(agent_workflow_state.get() or {}),
            last_refresh=last_refresh.get(),
        )
        yield pdf_bytes

    @render.ui
    def section_brief_all():
        return _section_brief_output("ALL")

    @render.ui
    def section_brief_business():
        return _section_brief_output("business")

    @render.ui
    def section_brief_arts():
        return _section_brief_output("arts")

    @render.ui
    def section_brief_technology():
        return _section_brief_output("technology")

    @render.ui
    def section_brief_world():
        return _section_brief_output("world")

    @render.ui
    def section_brief_politics():
        return _section_brief_output("politics")

    @render.ui
    def agent_workflow_panel():
        _ = signal_progress_tick.get()
        try:
            _ = input.signal_progress_ping()
        except Exception:
            pass
        state = dict(agent_workflow_state.get() or {})
        state["session_qc_metrics"] = dict(agent_session_qc_metrics.get() or {})
        status = str((state or {}).get("status", ""))
        return agent_workflow_ui(state, input.agent_view_mode())

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

    async def _run_research_brief_for_url(url: str) -> None:
        if not url or not str(url).strip():
            research_brief_state.set({"phase": "error", "text": "No article URL for research brief."})
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
        cards_t0 = time.perf_counter()
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
        try:
            active_tab = input.category_tabs()
        except Exception:
            active_tab = "ALL"
        if active_tab is None:
            active_tab = "ALL"
        first_paint_mode = (str(cat) == "ALL" and not first_cards_painted.get())
        lazy_summaries = str(cat) != str(active_tab) or first_paint_mode
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
            if not lazy_summaries and key not in summary_cache:
                title = row.get("title", "")
                abstract = row.get("abstract", "")
                sub = row.get("subtitle")
                sub = None if (sub is None or (isinstance(sub, float) and pd.isna(sub))) else sub
                to_fetch.append((str(title), str(abstract), str(sub) if sub else None))
                to_fetch_indices.append(i)
        if to_fetch:
            summaries = await asyncio.to_thread(get_summaries_parallel, to_fetch, tone, OPENAI_API_KEY)
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
            if lazy_summaries:
                abs_val = row.get("abstract", "")
                summ = str(abs_val) if abs_val is not None and not (isinstance(abs_val, float) and pd.isna(abs_val)) else ""
            else:
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
        if str(cat) == "ALL" and not first_cards_painted.get():
            first_cards_painted.set(True)
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
    import threading
    import webbrowser

    port = int(os.environ.get("PORT", 8000))
    # Browsers cannot open http://0.0.0.0 — use 127.0.0.1 for local dev. Set HOST=0.0.0.0 to listen on all interfaces (e.g. LAN); we still open localhost in the browser.
    host = os.environ.get("HOST", "127.0.0.1")
    open_url = f"http://127.0.0.1:{port}/"

    def _open_browser():
        webbrowser.open(open_url)

    if host == "0.0.0.0":
        threading.Timer(1.25, _open_browser).start()
        run_app(app, host=host, port=port, launch_browser=False)
    else:
        run_app(app, host=host, port=port, launch_browser=True)
