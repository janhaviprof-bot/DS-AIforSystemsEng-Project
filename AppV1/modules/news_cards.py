# news_cards.py - News card UI and image extraction

from shiny import ui


def get_image_url(article_row, placeholder_path: str = "placeholder.svg") -> str:
    """Get best image URL from article multimedia (article_row is a pandas Series)."""
    if article_row is None:
        return placeholder_path
    try:
        mm = article_row["multimedia"]
    except (KeyError, TypeError):
        return placeholder_path
    if mm is None:
        return placeholder_path
    if isinstance(mm, list) and len(mm) > 0:
        first = mm[0]
        if isinstance(first, dict) and "url" in first:
            return first["url"]
        if isinstance(first, str):
            return first
    if isinstance(mm, list):
        for item in mm:
            if isinstance(item, dict) and "url" in item:
                fmt = item.get("format", "")
                if fmt in ("mediumThreeByTwo210", "Normal", "mediumThreeByTwo440", "Standard Thumbnail", "thumbLarge"):
                    return item["url"]
        if mm and isinstance(mm[0], dict) and "url" in mm[0]:
            return mm[0]["url"]
    return placeholder_path


def _format_card_meta(section: str | None, published_date: str | None) -> str:
    """Format meta line for card: e.g. 'World · 2h ago' or 'Technology'."""
    parts = []
    if section:
        parts.append(section.strip())
    if published_date:
        parts.append(published_date.strip())
    return " · ".join(parts) if parts else ""


def news_card_ui(
    card_id: str,
    title: str,
    image_url: str,
    summary: str,
    url: str,
    is_breaking: bool = False,
    is_trending: bool = False,
    *,
    section: str | None = None,
    published_date: str | None = None,
) -> ui.TagList:
    """Render a single news card with optional section and published_date meta."""
    badge = ui.span(" ", class_="badge-placeholder")
    if is_breaking:
        badge = ui.span("BREAKING", class_="badge badge-breaking")
    elif is_trending:
        badge = ui.span("TRENDING", class_="badge badge-trending")
    meta_text = _format_card_meta(section, published_date)
    meta_line = ui.p(meta_text, class_="card-meta") if meta_text else None
    link_label = f"Read article: {title[:80]}{'…' if len(title) > 80 else ''}"
    body_children = []
    if meta_line:
        body_children.append(meta_line)
    read_nyt = ui.a(
        "Read on NYT",
        href=url,
        target="_blank",
        rel="noopener",
        class_="card-link",
        **{"aria-label": link_label},
    )
    footer = ui.div(read_nyt, class_="card-link-wrap")
    body_children.extend([
        ui.h4(ui.strong(title), class_="card-title"),
        ui.p(summary, class_="card-summary"),
        footer,
    ])
    return ui.div(
        ui.div(badge, class_="card-badge-area"),
        ui.img(src=image_url, alt=title, class_="card-image", style="object-fit: cover; width: 100%; height: 180px;"),
        ui.div(*body_children, class_="card-body"),
        class_="news-card",
    )
