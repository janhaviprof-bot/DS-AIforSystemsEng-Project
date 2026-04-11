# UI layout components — header, sidebar (improved labels & hints per UI/UX plan)

from shiny import ui


def app_header():
    """Sticky header with title and subtitle (styled via www/styles.css)."""
    return ui.div(
        ui.h1("News for People in Hurry"),
        ui.p("Stay informed with curated headlines from The New York Times", class_="subtitle"),
        class_="app-header",
    )


def sidebar_children():
    """Sidebar content: time range, sentiment, tone, refresh, feed stats.
    Labels and hints follow UI/UX recommendations for clarity.
    """
    return [
        ui.card(
            ui.card_header("⏱ Time range"),
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
            ui.card_header("Sentiment"),
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
            ui.card_header("Summary tone"),
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
            ui.card_header("View mode"),
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
            ui.input_action_button("refresh", "Refresh News", class_="btn-primary"),
            class_="control-card",
        ),
        ui.card(
            ui.card_header("📊 Overview"),
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
