# data_fetch.py - NYT Top Stories API fetching (robust version)

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_NYT_CACHE_TTL_SECONDS = 180
_nyt_cache: dict[str, object] = {"ts": None, "df": pd.DataFrame()}


def fetch_nyt_section(section: str, api_key: Optional[str], client: httpx.Client) -> pd.DataFrame:
    """Fetch articles from a single NYT Top Stories section. Returns empty DataFrame on failure."""
    if not api_key or not api_key.strip():
        return pd.DataFrame()
    # Top Stories API: no begin_date/end_date; request is URL only
    url = f"https://api.nytimes.com/svc/topstories/v2/{section}.json?api-key={api_key}"
    params_sent = {"section": section, "api_key_set": bool(api_key and api_key.strip())}
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            logger.warning("NYT section %s returned status %s", section, resp.status_code)
            return pd.DataFrame()
        data = resp.json()
        docs = data.get("results", [])
        logger.debug("NYT section=%s results=%s", section, len(docs))
        if data.get("status") != "OK" or not docs:
            return pd.DataFrame()
        df = pd.json_normalize(data["results"])
        df["fetched_from_section"] = section
        return df
    except Exception as e:
        logger.exception("NYT fetch failed for section %s: %s", section, e)
        return pd.DataFrame()


def fetch_nyt_articles(sections: list[str], api_key: Optional[str]) -> pd.DataFrame:
    """Fetch from multiple sections in parallel, merge and deduplicate. Never returns None."""
    now = datetime.now(timezone.utc)
    cached_df = _nyt_cache.get("df")
    cached_ts = _nyt_cache.get("ts")
    has_fresh_cache = (
        isinstance(cached_df, pd.DataFrame)
        and not cached_df.empty
        and isinstance(cached_ts, datetime)
        and (now - cached_ts) <= timedelta(seconds=_NYT_CACHE_TTL_SECONDS)
    )

    all_dfs = []
    with httpx.Client(timeout=30.0) as client:
        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = {executor.submit(fetch_nyt_section, s, api_key, client): s for s in sections}
            for future in as_completed(futures):
                df = future.result()
                if df is not None and not df.empty:
                    all_dfs.append(df)
    if not all_dfs:
        logger.warning("NYT API returned no articles from any section (check API key and network)")
        if has_fresh_cache:
            logger.warning(
                "Using cached NYT articles (%s rows, age=%ss) due to empty/429 response",
                len(cached_df),
                int((now - cached_ts).total_seconds()) if isinstance(cached_ts, datetime) else -1,
            )
            return cached_df.copy()
        return pd.DataFrame()
    combined = pd.concat(all_dfs, ignore_index=True)
    if "url" not in combined.columns:
        logger.warning("NYT response missing 'url' column")
        return pd.DataFrame()
    # Log which sections returned 0 articles (API may not have content for that section)
    if "fetched_from_section" in combined.columns:
        present = set(combined["fetched_from_section"].dropna().astype(str).str.strip().str.lower())
        for sec in sections:
            if sec.lower().strip() not in present:
                logger.warning("NYT API returned 0 articles for section '%s'", sec)
    agg = combined.groupby("url").agg(
        source_sections=("fetched_from_section", lambda x: ",".join(x.unique())),
        n_sections=("fetched_from_section", "nunique"),
    ).reset_index()
    combined = combined.drop_duplicates(subset=["url"], keep="first")
    combined = combined.merge(agg[["url", "n_sections"]], on="url", how="left")
    _nyt_cache["ts"] = now
    _nyt_cache["df"] = combined.copy()
    return combined


def filter_by_time(
    articles: Optional[pd.DataFrame],
    hours_ago: float | list[float] | tuple[float, float],
) -> pd.DataFrame:
    """Filter articles by published_date within time window. Never returns None."""
    if articles is None or articles.empty:
        return pd.DataFrame()
    if "published_date" not in articles.columns:
        logger.warning("filter_by_time: missing 'published_date', returning all articles")
        return articles
    try:
        pub = articles["published_date"]
        if not pd.api.types.is_datetime64_any_dtype(pub):
            pub = pd.to_datetime(pub, utc=True, errors="coerce")
        now = pd.Timestamp.now(tz="UTC")
        if isinstance(hours_ago, (list, tuple)) and len(hours_ago) >= 2:
            min_hrs, max_hrs = float(hours_ago[0]), float(hours_ago[1])
            cutoff_old = now - pd.Timedelta(hours=max_hrs)
            cutoff_new = now - pd.Timedelta(hours=min_hrs)
            mask = (pub >= cutoff_old) & (pub <= cutoff_new)
        else:
            cutoff = now - pd.Timedelta(hours=float(hours_ago))
            mask = pub >= cutoff
        out = articles.loc[mask].reset_index(drop=True)
        if out.empty and not articles.empty:
            logger.warning("filter_by_time: time window removed all %s articles; returning all", len(articles))
            return articles
        return out
    except Exception as e:
        logger.exception("filter_by_time failed: %s", e)
        return articles
