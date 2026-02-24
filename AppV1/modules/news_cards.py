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


def news_card_ui(
    card_id: str,
    title: str,
    image_url: str,
    summary: str,
    url: str,
    is_breaking: bool = False,
    is_trending: bool = False,
) -> ui.TagList:
    """Render a single news card. At most 2 cards should show BREAKING, at most 2 should show TRENDING."""
    badge = ui.span(" ", class_="badge-placeholder")  # Reserve space so cards don't shift
    if is_breaking:
        badge = ui.span("BREAKING", class_="badge badge-breaking")
    elif is_trending:
        badge = ui.span("TRENDING", class_="badge badge-trending")
    return ui.div(
        ui.div(badge, class_="card-badge-area"),
        ui.img(src=image_url, alt=title, class_="card-image", style="object-fit: cover; width: 100%; height: 180px;"),
        ui.div(
            ui.h4(ui.strong(title), class_="card-title"),
            ui.p(summary, class_="card-summary"),
            ui.div(
                ui.a("Read more...", href=url, target="_blank", rel="noopener", class_="card-link"),
                class_="card-link-wrap",
            ),
            class_="card-body",
        ),
        class_="news-card",
    )
