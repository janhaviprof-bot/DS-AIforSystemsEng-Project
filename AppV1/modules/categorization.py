# categorization.py - Breaking, trending, latest logic

from typing import Optional

import pandas as pd


def add_breaking_tag(articles: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Add breaking tag (published < 2 hours ago). Never returns None."""
    if articles is None or articles.empty:
        return pd.DataFrame()
    if "published_date" not in articles.columns:
        return articles.copy()
    cutoff_2hr = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    out = articles.copy()
    out["is_breaking"] = out["published_date"] >= cutoff_2hr
    return out


def _safe_facets(x) -> list:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return []
    if isinstance(x, list):
        return [str(v) for v in x]
    if hasattr(x, "tolist"):
        return [str(v) for v in x.tolist()]
    return [str(x)]


def compute_trending_score(articles: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Trending score: 0.4*des_facet + 0.3*updated + 0.2*multimedia + 0.1*multi_section. Never returns None."""
    if articles is None or articles.empty:
        return pd.DataFrame()
    articles = articles.copy()
    n = len(articles)
    des_facet_col = articles.get("des_facet")
    if des_facet_col is None:
        des_facet_col = [list()] * n
    facet_lists: list[list[str]] = []
    facet_frequency: dict[str, int] = {}
    for i in range(n):
        facets = list(dict.fromkeys(_safe_facets(des_facet_col.iloc[i] if hasattr(des_facet_col, "iloc") else des_facet_col[i])))
        facet_lists.append(facets)
        for facet in facets:
            facet_frequency[facet] = facet_frequency.get(facet, 0) + 1
    facet_counts = []
    for facets in facet_lists:
        if not facets:
            facet_counts.append(0)
            continue
        facet_counts.append(sum(max(facet_frequency.get(facet, 0) - 1, 0) for facet in facets))
    max_facet = max(max(facet_counts), 1)
    des_score = [c / max_facet for c in facet_counts]
    if "updated_date" in articles.columns and "published_date" in articles.columns:
        has_updated = (
            articles["updated_date"].notna()
            & articles["published_date"].notna()
            & (articles["updated_date"] != articles["published_date"])
        )
    else:
        has_updated = pd.Series([False] * n)
    updated_score = has_updated.astype(float).tolist()
    multi_col = articles.get("multimedia")
    if multi_col is not None:
        multi_len = []
        for v in multi_col:
            if isinstance(v, list) and len(v) > 0:
                multi_len.append(1)
            elif isinstance(v, dict) or (hasattr(v, "__len__") and not isinstance(v, str) and len(v) > 0):
                multi_len.append(1)
            else:
                multi_len.append(0)
    else:
        multi_len = [0] * n
    multimedia_score = [float(x) for x in multi_len]
    n_sec = articles.get("n_sections")
    if n_sec is not None:
        multi_section_score = (n_sec >= 2).astype(float).tolist()
    else:
        multi_section_score = [0.0] * n
    articles["trending_score"] = [
        0.4 * d + 0.3 * u + 0.2 * m + 0.1 * s
        for d, u, m, s in zip(des_score, updated_score, multimedia_score, multi_section_score)
    ]
    articles["is_trending"] = articles["trending_score"] > 0.5
    return articles


def sort_latest(articles: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Sort articles by published_date descending. Never returns None."""
    if articles is None or articles.empty:
        return pd.DataFrame()
    if "published_date" not in articles.columns:
        return articles.copy()
    return articles.sort_values("published_date", ascending=False).reset_index(drop=True)


def filter_by_category(articles: Optional[pd.DataFrame], category: str) -> pd.DataFrame:
    """Filter articles for category tab (ALL or specific section). Never returns None."""
    if articles is None or articles.empty:
        return pd.DataFrame()
    if category == "ALL":
        return articles.copy()
    # Normalize category and section values (case-insensitive, trimmed)
    cat_lower = str(category).strip().lower()
    sec = (
        articles.get("section", pd.Series([""] * len(articles)))
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    fetched = (
        articles.get("fetched_from_section", pd.Series([""] * len(articles)))
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    mask = (
        (sec == cat_lower)
        | (fetched == cat_lower)
        | sec.str.contains(cat_lower, regex=False)
        | fetched.str.contains(cat_lower, regex=False)
    )
    return articles[mask].reset_index(drop=True)


def select_first_six(articles: Optional[pd.DataFrame]) -> pd.DataFrame:
    """First 6: 2 breaking, 2 trending, 2 latest (no duplicates). Backfill from latest if < 6."""
    if articles is None or articles.empty:
        return pd.DataFrame()
    arts = sort_latest(articles)
    if arts.empty:
        return pd.DataFrame()
    if "url" not in arts.columns or "is_breaking" not in arts.columns or "is_trending" not in arts.columns:
        return arts.head(6)
    used = []
    breaking = arts[arts["is_breaking"]].sort_values("published_date", ascending=False)
    b2 = breaking.head(2)
    used.extend(b2["url"].tolist())
    trending = arts[arts["is_trending"] & ~arts["url"].isin(used)].sort_values("trending_score", ascending=False)
    t2 = trending.head(2)
    used.extend(t2["url"].tolist())
    latest = arts[~arts["url"].isin(used)]
    l2 = latest.head(2)
    result = pd.concat([b2, t2, l2], ignore_index=True)
    used = result["url"].tolist()
    remaining = arts[~arts["url"].isin(used)]
    need = 6 - len(result)
    if need > 0 and len(remaining) > 0:
        extra = remaining.head(need)
        result = pd.concat([result, extra], ignore_index=True)
    return result


def select_next_six(articles: Optional[pd.DataFrame], exclude_urls: list) -> pd.DataFrame:
    """Next 6 from Latest rank only (pagination). Never returns None."""
    if articles is None or articles.empty:
        return pd.DataFrame()
    arts = sort_latest(articles)
    if arts.empty or "url" not in arts.columns:
        return pd.DataFrame()
    arts = arts[~arts["url"].isin(exclude_urls)]
    return arts.head(6)
