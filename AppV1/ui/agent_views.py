from shiny import ui


def _help_icon(text: str) -> ui.TagChild:
    tip = _compact_text(text)
    return ui.tags.span(
        "?",
        class_="feature-help-icon",
        title=tip,
        aria_label=tip,
        tabindex="0",
        role="img",
    )


def _compact_text(value, fallback: str = "") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _title_case(value, fallback: str = "") -> str:
    text = _compact_text(value, fallback)
    return text.title() if text else ""


def _truncate(text: str, limit: int = 150) -> str:
    clean = _compact_text(text)
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _expandable_pipeline_copy(raw: str, limit: int) -> ui.TagChild:
    """Same truncated preview as before; full text in a native <details> expand (no new content)."""
    full = _compact_text(str(raw or ""), "")
    if not full:
        return ui.p("—", class_="pipeline-card-copy")
    if len(full) <= limit:
        return ui.p(full, class_="pipeline-card-copy")
    preview = _truncate(full, limit)
    return ui.tags.details(
        ui.tags.summary(preview, class_="pipeline-card-summary"),
        ui.p(full, class_="pipeline-card-copy pipeline-card-copy-expanded"),
        class_="pipeline-card-details",
    )


def _as_text_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _compact_text(value)
        return [text] if text else []
    if isinstance(value, dict):
        value = [value]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, dict):
                parts = [
                    _compact_text(item.get("statement", "")),
                    _compact_text(item.get("market_response", "")),
                    _compact_text(item.get("trigger", "")),
                ]
                text = " | ".join(part for part in parts if part)
            else:
                text = _compact_text(item)
            if text:
                out.append(text)
        return out
    text = _compact_text(value)
    return [text] if text else []


def _score_fill(score: int) -> float:
    score = max(-100, min(100, int(score)))
    return (score + 100) / 2


def _market_signal_label(score: int, market_agreement: str) -> tuple[str, str]:
    agreement = market_agreement.lower().strip()
    if score <= -15 and agreement in {"aligned", "mixed", "partial alignment"}:
        return ("Risk-off", "Bearish bias")
    if score >= 15 and agreement in {"aligned", "mixed", "partial alignment"}:
        return ("Risk-on", "Bullish bias")
    return ("Watchful", "Mixed bias")


def _confidence_score(agent1: dict, agent3: dict, market: dict) -> int:
    base = 52
    base += min(18, len(agent1.get("connections", []) or []) * 6)
    if str(agent3.get("market_agreement", "")).lower().strip() in {"aligned", "partial alignment", "mixed"}:
        base += 10
    if market.get("instruments"):
        base += 8
    return max(20, min(92, base))


def _summary_card(label: str, value: str, subtitle: str, tone: str = "neutral", meter: float | None = None) -> ui.TagChild:
    meter_ui = ui.div(class_="signal-stat-meter-empty")
    if meter is not None:
        meter_ui = ui.div(
            ui.div(class_=f"signal-stat-meter-fill signal-stat-meter-fill-{tone}", style=f"width:{max(6.0, min(100.0, meter)):.1f}%;"),
            class_="signal-stat-meter",
        )
    return ui.div(
        ui.p(label, class_="signal-stat-label"),
        ui.p(value, class_=f"signal-stat-value signal-stat-value-{tone}"),
        ui.p(subtitle, class_="signal-stat-subtitle"),
        meter_ui,
        class_="signal-stat-card",
    )


def _pill(text: str, tone: str = "neutral") -> ui.TagChild:
    return ui.span(text, class_=f"signal-pill signal-pill-{tone}")


def _sparkbars(move: float) -> str:
    if move > 0.8:
        return "▃▅▆▇▇▆▅"
    if move > 0.2:
        return "▂▃▄▅▆▆▇"
    if move > -0.2:
        return "▄▄▅▄▅▄▅"
    if move > -0.8:
        return "▇▆▅▄▃▂▁"
    return "▇▇▆▅▄▃▂"


def _market_pulse_rows(instruments: list[dict]) -> ui.TagChild:
    if not instruments:
        return ui.p("Market data unavailable.", class_="signal-empty-copy")
    rows = []
    for item in instruments[:5]:
        move = float(item.get("pct_change", 0.0))
        tone = "up" if move > 0 else "down" if move < 0 else "flat"
        rows.append(
            ui.div(
                ui.span(str(item.get("label", "")), class_="pulse-label"),
                ui.span(_sparkbars(move), class_=f"pulse-bars pulse-bars-{tone}"),
                ui.span(f"{move:+.2f}%", class_=f"pulse-value pulse-value-{tone}"),
                class_="pulse-row",
            )
        )
    return ui.div(*rows, class_="pulse-grid")


def _causal_flow(connections: list[dict]) -> ui.TagChild:
    if not connections:
        return ui.p("Causal flow is updating.", class_="signal-empty-copy")
    rows = []
    for item in connections[:3]:
        trigger = _compact_text(item.get("trigger", "Live trigger"))
        theme = _compact_text(item.get("theme", "Cross-section shift"))
        sections = [str(s) for s in item.get("sections", []) if str(s).strip()]
        rows.append(
            ui.div(
                _pill(trigger, "trigger"),
                ui.span("→", class_="flow-arrow"),
                _pill(theme, "theme"),
                ui.span("→", class_="flow-arrow"),
                ui.div(*[_pill(sec, "section") for sec in sections[:3]], class_="flow-section-cluster"),
                class_="flow-row",
            )
        )
    return ui.div(*rows, class_="flow-grid")


def _category_signal_card(packet: dict) -> ui.TagChild:
    counts = packet.get("sentiment_counts", {}) or {}
    pos = int(counts.get("positive", 0))
    neg = int(counts.get("negative", 0))
    neu = int(counts.get("neutral", 0))
    dots = []
    dots.extend([ui.span(class_="signal-dot signal-dot-positive") for _ in range(min(pos, 3))])
    dots.extend([ui.span(class_="signal-dot signal-dot-negative") for _ in range(min(neg, 3))])
    dots.extend([ui.span(class_="signal-dot signal-dot-neutral") for _ in range(min(neu, 3))])
    score_label = f"{pos}:{neg}:{neu}"
    return ui.div(
        ui.p(str(packet.get("label", "")), class_="category-card-title"),
        ui.div(
            ui.div(*dots, class_="category-dot-row"),
            ui.span(score_label, class_="category-dot-score"),
            class_="category-dot-meta",
        ),
        ui.p(_truncate(str(packet.get("brief", "")), 88), class_="category-card-copy"),
        class_="category-card",
    )


def _detail_block(title: str, body: ui.TagChild) -> ui.TagChild:
    return ui.tags.details(
        ui.tags.summary(title, class_="signal-detail-summary"),
        ui.div(body, class_="signal-detail-body"),
        class_="signal-detail",
    )


def _signal_progress(state: dict) -> ui.TagChild:
    status = str(state.get("status", "idle"))
    pct_raw = state.get("progress_pct", 0)
    try:
        pct = int(pct_raw)
    except Exception:
        pct = 0
    pct = max(0, min(100, pct))
    label = _compact_text(state.get("progress_label", ""), "")
    if not label:
        label = {
            "idle": "Waiting",
            "loading": "Loading",
            "ready": "Done" if pct >= 100 else "Finalizing",
            "error": "Retry needed",
        }.get(status, "Loading")
    show_spinner = pct < 100 and status != "error"
    return ui.div(
        ui.div(
            ui.div(
                ui.span(id="signal-progress-spinner", class_="signal-progress-spinner")
                if show_spinner
                else ui.span(id="signal-progress-spinner", class_="signal-progress-spinner signal-progress-spinner-hidden"),
                ui.span("Signal Studio", class_="signal-progress-label"),
                class_="signal-progress-left",
            ),
            ui.span(f"{pct}%", id="signal-progress-pct", class_="signal-progress-pct"),
            class_="signal-progress-row",
        ),
        ui.div(
            ui.div(id="signal-progress-fill", class_="signal-progress-fill", style=f"width:{pct}%;"),
            class_="signal-progress-track",
        ),
        ui.p(label, id="signal-progress-note", class_="signal-progress-note"),
        class_="signal-progress-wrap",
    )


def _insight_slides(state: dict) -> list[dict[str, str]]:
    workflow = state.get("workflow", {}) or {}
    agent1 = workflow.get("agent1", {}) or {}
    agent2 = workflow.get("agent2", {}) or {}
    agent3 = workflow.get("agent3", {}) or {}
    market = workflow.get("market_snapshot", {}) or {}
    score = int(agent2.get("world_mood_score", 0) or 0)
    mood = _title_case(agent2.get("world_mood_label", "Mixed"), "Mixed")
    agreement = _title_case(agent3.get("market_agreement", "Mixed"), "Mixed")
    signal, _ = _market_signal_label(score, str(agent3.get("market_agreement", "mixed")))
    connections = list(agent1.get("connections", []) or [])
    first_connection = connections[0] if connections else {}
    second_connection = connections[1] if len(connections) > 1 else {}
    avg_change = float(market.get("avg_change", 0.0) or 0.0)
    instruments = list(market.get("instruments", []) or [])
    strongest = None
    if instruments:
        strongest = max(instruments, key=lambda item: abs(float(item.get("pct_change", 0.0) or 0.0)))
    slides = [
        {
            "emoji": "🌍",
            "label": "Global Signal",
            "title": f"{signal} mood with {mood.lower()} bias",
            "detail": f"World score {score:+d} with {agreement.lower()} market confirmation.",
            "tone": "neutral",
        }
    ]
    if first_connection:
        slides.append(
            {
                "emoji": "⚠️",
                "label": "Driver",
                "title": _compact_text(first_connection.get("trigger", "Geopolitical pressure")),
                "detail": _truncate(first_connection.get("theme", "Cross-section pressure is building."), 86),
                "tone": "danger",
            }
        )
    if second_connection:
        slides.append(
            {
                "emoji": "🤖",
                "label": "Driver",
                "title": _compact_text(second_connection.get("trigger", "AI pressure rising")),
                "detail": _truncate(second_connection.get("theme", "Tech uncertainty is spreading."), 86),
                "tone": "theme",
            }
        )
    market_title = f"Broad move {avg_change:+.2f}%"
    market_detail = "Market pulse is still forming."
    if strongest:
        market_detail = f"{_compact_text(strongest.get('label', 'Market'))} is moving {float(strongest.get('pct_change', 0.0) or 0.0):+.2f}%."
    slides.append(
        {
            "emoji": "📉" if avg_change < 0 else "📈",
            "label": "Market",
            "title": market_title,
            "detail": market_detail,
            "tone": "market" if avg_change >= 0 else "danger",
        }
    )
    slides.append(
        {
            "emoji": "🎯",
            "label": "Alignment",
            "title": f"{agreement} between headlines and markets",
            "detail": _truncate(agent3.get("final_insight", "") or state.get("marquee_text", ""), 86),
            "tone": "positive" if "align" in agreement.lower() else "neutral",
        }
    )
    return slides[:5]


def _insight_marquee_inner(slides: list[dict[str, str]], *, aria_hidden: bool = False) -> ui.TagChild:
    """One horizontal row of segments: same order and fields as the old carousel slides."""
    parts: list = []
    n = len(slides)
    for i, slide in enumerate(slides):
        tone = slide["tone"]
        parts.extend(
            [
                ui.span(slide["emoji"], class_="insight-marquee-emoji"),
                ui.span(slide["label"], class_=f"insight-marquee-chip insight-marquee-chip-{tone}"),
                ui.span(slide["title"], class_=f"insight-marquee-strong insight-marquee-strong-{tone}"),
                ui.span("—", class_="insight-marquee-em"),
                ui.span(slide["detail"], class_=f"insight-marquee-detail insight-marquee-detail-{tone}"),
            ]
        )
        if i < n - 1:
            parts.append(ui.span(" · ", class_="insight-marquee-sep"))
    kwargs = {}
    if aria_hidden:
        kwargs["aria_hidden"] = "true"
    return ui.div(*parts, class_="insight-marquee-inner", **kwargs)


def agent_marquee_ui(state: dict) -> ui.TagChild:
    status = str(state.get("status", "idle"))
    status_label = {
        "idle": "Idle",
        "loading": "Analyzing",
        "ready": "Live",
        "error": "Fallback",
    }.get(status, "Live")
    slides = _insight_slides(state)
    if not slides:
        slides = [
            {
                "emoji": "🌍",
                "label": "Global Signal",
                "title": "Insight stream will appear after refresh",
                "detail": "The agent pipeline is waiting for the next live run.",
                "tone": "neutral",
            }
        ]
    inner_a = _insight_marquee_inner(slides)
    inner_b = _insight_marquee_inner(slides, aria_hidden=True)
    return ui.div(
        ui.div(
            ui.span("Global Insight", class_="insight-label insight-label-in-header"),
            ui.span(status_label, class_=f"insight-status insight-status-{status} insight-status-in-header"),
            class_="insight-header insight-header-in-bar",
        ),
        ui.div(
            ui.div(
                inner_a,
                inner_b,
                class_="insight-marquee-track",
            ),
            class_="insight-marquee-viewport",
            role="region",
            aria_label="Global insight ticker",
        ),
        class_="agent-marquee-shell agent-marquee-in-header",
    )


def section_brief_ui(label: str, summary: str, counts: dict | None = None, help_text: str | None = None) -> ui.TagChild:
    counts = counts or {}
    pos = int(counts.get("positive", 0))
    neg = int(counts.get("negative", 0))
    neu = int(counts.get("neutral", 0))
    return ui.div(
        ui.div(
            ui.span(f"{label} Brief", class_="section-brief-title"),
            _help_icon(help_text or "Briefly explains the top themes and sentiment in this section."),
            class_="section-brief-top",
        ),
        ui.div(
            ui.span(
                ui.span("Positive", class_="section-sentiment-label"),
                ui.span(str(pos), class_="section-sentiment-count"),
                class_="section-sentiment-pill section-sentiment-pill-positive",
            ),
            ui.span(
                ui.span("Negative", class_="section-sentiment-label"),
                ui.span(str(neg), class_="section-sentiment-count"),
                class_="section-sentiment-pill section-sentiment-pill-negative",
            ),
            ui.span(
                ui.span("Neutral", class_="section-sentiment-label"),
                ui.span(str(neu), class_="section-sentiment-count"),
                class_="section-sentiment-pill section-sentiment-pill-neutral",
            ),
            class_="section-sentiment-row",
        ),
        ui.tags.details(
            ui.tags.summary(
                ui.span("▾", class_="section-brief-summary-chevron"),
                ui.span("Brief", class_="section-brief-summary-text"),
                class_="section-brief-summary",
            ),
            ui.div(
                ui.p(summary or "This section is updating.", class_="section-brief-copy"),
                class_="section-brief-body",
            ),
            class_="section-brief-details",
            open="",
        ),
        class_="section-brief-card",
    )


def _signal_studio_about_panel() -> ui.TagChild:
    """Collapsible explainer for the Signal Studio tab (closed by default)."""
    return ui.tags.details(
        ui.tags.summary(
            ui.span("▾", class_="signal-studio-about-chevron"),
            ui.span("About Signal Studio", class_="signal-studio-about-summary-label"),
            class_="signal-studio-about-summary",
        ),
        ui.div(
            ui.p(
                "This tab reads your current news window and builds a quick ",
                ui.tags.strong("situation picture"),
                ": how stories connect across topics, what the overall tone feels like, "
                "and whether major market moves broadly match that story.",
                class_="signal-studio-about-lead",
            ),
            ui.p("How it works, in order:", class_="signal-studio-about-subhead"),
            ui.tags.ol(
                ui.tags.li(
                    ui.tags.strong("Cross-section links"),
                    " — Surfaces themes that show up across more than one area (e.g. business, world, tech).",
                ),
                ui.tags.li(
                    ui.tags.strong("Global mood"),
                    " — Summarizes whether the mix of headlines feels more upbeat, cautious, or mixed.",
                ),
                ui.tags.li(
                    ui.tags.strong("Market check"),
                    " — Compares that narrative to a live snapshot of major markets so you can see alignment or tension.",
                ),
                class_="signal-studio-about-steps",
            ),
            ui.p(
                "Numbers and cards refresh when you ",
                ui.tags.strong("Refresh News"),
                " (and match your time range and filters). "
                "This is AI-assisted interpretation plus public market data—not trading advice.",
                class_="signal-studio-about-foot",
            ),
            class_="signal-studio-about-body",
        ),
        class_="signal-studio-about",
    )


def agent_workflow_ui(state: dict, mode: str = "Minimal") -> ui.TagChild:
    status = str(state.get("status", "idle"))
    workflow = state.get("workflow", {}) or {}
    agent1 = workflow.get("agent1", {}) or {}
    agent2 = workflow.get("agent2", {}) or {}
    agent3 = workflow.get("agent3", {}) or {}
    market = workflow.get("market_snapshot", {}) or {}
    section_packets = state.get("sections", []) or []

    if status == "loading":
        return ui.div(
            _signal_studio_about_panel(),
            ui.div(
                ui.h3("Signal Studio is running", class_="agent-workflow-title"),
                ui.p("The agents are linking sections, rating global mood, and checking market confirmation.", class_="agent-workflow-subtitle"),
                _signal_progress(state),
                class_="agent-workflow-loading",
            ),
            class_="agent-workflow-tab-root",
        )
    if status == "idle":
        return ui.div(
            _signal_studio_about_panel(),
            ui.div(
                ui.h3("Signal Studio", class_="agent-workflow-title"),
                ui.p("Refresh the news to generate the live signal dashboard.", class_="agent-workflow-subtitle"),
                _signal_progress(state),
                class_="agent-workflow-loading",
            ),
            class_="agent-workflow-tab-root",
        )
    if status == "error":
        return ui.div(
            _signal_studio_about_panel(),
            ui.div(
                ui.h3("Signal Studio fallback", class_="agent-workflow-title"),
                ui.p("The workflow hit an LLM or market-data issue, so the dashboard is waiting for the next clean run.", class_="agent-workflow-subtitle"),
                _signal_progress(state),
                class_="agent-workflow-loading",
            ),
            class_="agent-workflow-tab-root",
        )

    mood_label = _title_case(agent2.get("world_mood_label", "Mixed"), "Mixed")
    score = int(agent2.get("world_mood_score", 0) or 0)
    market_bias = _title_case(market.get("market_bias", "Mixed"), "Mixed")
    avg_change = float(market.get("avg_change", 0.0) or 0.0)
    agreement_raw = _compact_text(agent3.get("market_agreement", "mixed"), "mixed")
    agreement_label = _title_case(agreement_raw.replace("_", " "), "Mixed")
    signal_label, signal_subtitle = _market_signal_label(score, agreement_raw)
    confidence = _confidence_score(agent1, agent3, market)

    stat_row = ui.div(
        _summary_card("World mood", f"{score:+d}", mood_label, "danger" if score < 0 else "positive", _score_fill(score)),
        _summary_card("Market", market_bias, f"Avg {avg_change:+.2f}%", "market"),
        _summary_card("Signal", signal_label, signal_subtitle, "danger" if signal_label == "Risk-off" else "market"),
        _summary_card("Confidence", f"{confidence}%", "Moderate" if confidence < 75 else "High", "neutral", confidence),
        class_="signal-stat-grid",
    )

    pipeline_row = ui.div(
        ui.div(
            ui.p("Agent 1 · correlation", class_="pipeline-card-kicker"),
            ui.h3("Cross-section links", class_="pipeline-card-title"),
            _expandable_pipeline_copy(agent1.get("cross_section_summary", ""), 120),
            _pill(f"{len(agent1.get('connections', []) or [])} triggers found", "tag-warm"),
            class_="pipeline-card pipeline-card-done",
        ),
        ui.div(
            ui.p("Agent 2 · sentiment", class_="pipeline-card-kicker"),
            ui.h3("Global mood rating", class_="pipeline-card-title"),
            _expandable_pipeline_copy(agent2.get("description", ""), 120),
            _pill(f"{mood_label} overall", "tag-danger" if score < 0 else "tag-positive"),
            class_="pipeline-card pipeline-card-done",
        ),
        ui.div(
            ui.p("Agent 3 · market check", class_="pipeline-card-kicker"),
            ui.h3("News vs reality", class_="pipeline-card-title"),
            _expandable_pipeline_copy(agent3.get("final_insight", ""), 132),
            _pill(agreement_label, "tag-positive" if "align" in agreement_label.lower() else "tag-warm"),
            class_="pipeline-card pipeline-card-done",
        ),
        class_="pipeline-grid",
    )

    category_cards = [packet for packet in section_packets if str(packet.get("section")) in {"business", "arts", "world", "politics"}]

    detail_blocks = []
    if mode in {"Analytical", "Deep Dive"}:
        detail_blocks.append(
            _detail_block(
                "Open analytical notes",
                ui.tags.ul(*[ui.tags.li(text) for text in _as_text_list(agent2.get("reasoning", []))[:4]], class_="agent-list"),
            )
        )
    if mode == "Deep Dive":
        detail_blocks.append(
            _detail_block(
                "Open market validation details",
                ui.tags.ul(*[ui.tags.li(text) for text in _as_text_list(agent3.get("truth_checks", []))[:5]], class_="agent-list"),
            )
        )

    return ui.div(
        _signal_studio_about_panel(),
        _signal_progress(state),
        stat_row,
        pipeline_row,
        ui.div(
            ui.div(
                ui.h3("Causal flow (Agent 1)", class_="agent-workflow-title"),
                _causal_flow(list(agent1.get("connections", []))),
                class_="signal-panel signal-panel-large",
            ),
            ui.div(
                ui.h3("Market pulse (Agent 3)", class_="agent-workflow-title"),
                _market_pulse_rows(list(market.get("instruments", []))),
                class_="signal-panel",
            ),
            class_="signal-main-grid",
        ),
        ui.div(
            ui.h3("Category signals (Agent 2)", class_="agent-workflow-title"),
            ui.div(*[_category_signal_card(packet) for packet in category_cards], class_="category-signal-grid"),
            class_="signal-panel",
        ),
        ui.div(
            ui.p("Final insight", class_="final-insight-label"),
            ui.p(_compact_text(agent3.get("final_insight", "") or agent2.get("description", "")), class_="final-insight-copy"),
            class_="final-insight-bar",
        ),
        ui.div(*detail_blocks, class_="dashboard-detail-grid") if detail_blocks else ui.div(),
        class_="agent-workflow-shell signal-dashboard-shell",
    )
