# UI layout components — header, sidebar (improved labels & hints per UI/UX plan)

from shiny import ui


def help_icon(text: str) -> ui.TagChild:
    """Small hover-help icon with tooltip and screen-reader label."""
    tip = " ".join(str(text or "").split())
    return ui.tags.span(
        "?",
        class_="feature-help-icon",
        title=tip,
        aria_label=tip,
        tabindex="0",
        role="img",
    )


def feature_header(label: str, help_text: str) -> ui.TagChild:
    """Left title + right help icon row."""
    return ui.div(
        ui.span(label, class_="feature-header-label"),
        help_icon(help_text),
        class_="feature-header-row",
    )


def app_header():
    """Sticky header with title and subtitle (styled via www/styles.css)."""
    return ui.div(
        ui.h1("News for People in Hurry"),
        ui.p("Stay informed with curated headlines from The New York Times", class_="subtitle"),
        class_="app-header",
    )


def app_header_with_marquee(marquee: ui.TagChild):
    """Title header plus separate Global Insight card below."""
    return ui.div(
        ui.div(
            ui.div(
                ui.h1("News for People in Hurry"),
                ui.p("Stay informed with curated headlines from The New York Times", class_="subtitle"),
                class_="app-header-brand",
            ),
            class_="app-header app-header-title-only",
        ),
        ui.div(marquee, class_="app-header-insight-wrap"),
        class_="app-header-stack",
    )


def sidebar_children():
    """Sidebar content: time range, sentiment, tone, refresh, feed stats.
    Labels and hints follow UI/UX recommendations for clarity.
    """
    return [
        ui.card(
            ui.card_header(feature_header("⏱ Time range", "Choose how far back to include news. Higher hours includes older stories.")),
            ui.input_slider(
                "time_hours",
                "Last 6–48 hours",
                6,
                48,
                value=24,
                step=1,
            ),
            class_="control-card",
        ),
        ui.card(
            ui.card_header(feature_header("Sentiment", "Filter stories by positive, negative, or neutral tone. Leave all unchecked to show all.")),
            ui.input_checkbox_group(
                "sentiment",
                None,
                choices={
                    "positive": "😊 Positive",
                    "negative": "😟 Negative",
                    "neutral": "😐 Neutral",
                },
                inline=False,
            ),
            ui.p("Leave all unchecked to show all.", class_="stats-hint"),
            class_="control-card",
        ),
        ui.card(
            ui.card_header(feature_header("Summary tone", "Controls writing style for AI summaries only. It does not change which stories are shown.")),
            ui.input_radio_buttons(
                "tone",
                None,
                choices={
                    "Informational": "ℹ️ Informational",
                    "Opinion": "💭 Opinion",
                    "Analytical": "📊 Analytical",
                },
                selected="Informational",
            ),
            ui.p(
                "Affects the tone of AI-generated summaries.",
                class_="stats-hint",
            ),
            class_="control-card",
        ),
        ui.card(
            ui.card_header(feature_header("View mode (Signal Studio)", "Sets how much detail appears in Signal Studio: Minimal, Analytical, or Deep dive.")),
            ui.input_radio_buttons(
                "agent_view_mode",
                None,
                choices={
                    "Minimal": "Minimal",
                    "Analytical": "Analytical",
                    "Deep Dive": "Deep dive",
                },
                selected="Minimal",
            ),
            ui.p("Controls how much agent detail is shown in the workflow tab.", class_="stats-hint"),
            class_="control-card",
        ),
        ui.card(
            feature_header("Refresh News", "Fetch latest headlines and rerun enrichment for current filters and time range."),
            ui.input_action_button("refresh", "Refresh News", class_="btn-primary"),
            class_="control-card",
        ),
        ui.card(
            ui.card_header(feature_header("📊 Overview", "Quick feed stats: total articles, tags, update time, and sentiment mix.")),
            ui.output_ui("sidebar_stats"),
            class_="control-card stats-card",
        ),
    ]


def empty_state_message(
    no_articles_loaded: bool = False,
    sentiment_filter_active: bool = False,
    category_label: str = "articles",
) -> ui.TagChild:
    """Empty state with icon and short guidance (per UI/UX plan)."""
    if no_articles_loaded:
        headline = "No articles loaded."
        hint = "Add NYT_API_KEY to .env and click Refresh News."
    elif sentiment_filter_active:
        headline = f"No {category_label} match the selected sentiment."
        hint = "Clear the sentiment filter (leave all unchecked) or try another tab."
    else:
        headline = f"No {category_label} in this time range."
        hint = "Try the All tab or increase the time range (e.g. 48 hrs)."
    return ui.div(
        ui.div("📰", class_="empty-state-icon"),
        ui.p(headline + " " + hint),
        class_="empty-state",
    )


def pagination_bar(
    prev_id: str,
    next_id: str,
    page_context_id: str,
) -> ui.TagList:
    """Previous / page context / Next bar (accessibility-friendly labels)."""
    return ui.div(
        ui.div(ui.output_ui(page_context_id), class_="pagination-context"),
        ui.div(
            ui.input_action_button(prev_id, "Previous page", class_="btn-secondary"),
            ui.input_action_button(next_id, "Next page", class_="btn-primary"),
            class_="pagination-buttons",
        ),
        class_="pagination-bar",
    )
