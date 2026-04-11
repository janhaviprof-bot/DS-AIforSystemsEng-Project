import logging
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)
MARKET_CACHE_TTL = timedelta(minutes=10)
_market_cache: dict[str, Any] = {"expires_at": None, "payload": None}

MARKET_TICKERS = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "^DJI": "Dow",
    "GC=F": "Gold",
    "CL=F": "Crude Oil",
    "BTC-USD": "Bitcoin",
}


def _instrument_snapshot(symbol: str, label: str) -> dict[str, Any] | None:
    try:
        history = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
        if history is None or history.empty or "Close" not in history:
            return None
        closes = history["Close"].dropna()
        if len(closes) < 2:
            return None
        latest = float(closes.iloc[-1])
        previous = float(closes.iloc[-2])
        if previous == 0:
            return None
        pct_change = ((latest - previous) / previous) * 100
        return {
            "symbol": symbol,
            "label": label,
            "last_close": round(latest, 2),
            "pct_change": round(pct_change, 2),
            "direction": "up" if pct_change > 0 else "down" if pct_change < 0 else "flat",
        }
    except Exception as exc:
        logger.warning("Market fetch failed for %s: %s", symbol, exc)
        return None


def fetch_market_snapshot() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires_at = _market_cache.get("expires_at")
    cached_payload = _market_cache.get("payload")
    if cached_payload and isinstance(expires_at, datetime) and now < expires_at:
        return cached_payload
    instruments = []
    for symbol, label in MARKET_TICKERS.items():
        snap = _instrument_snapshot(symbol, label)
        if snap:
            instruments.append(snap)
    if not instruments:
        payload = {
            "summary": "Live market data is unavailable right now.",
            "market_bias": "unknown",
            "avg_change": 0.0,
            "instruments": [],
            "leaders": [],
            "laggards": [],
        }
        _market_cache["payload"] = payload
        _market_cache["expires_at"] = now + MARKET_CACHE_TTL
        return payload
    avg_change = round(mean(item["pct_change"] for item in instruments), 2)
    positive_count = sum(1 for item in instruments if item["pct_change"] > 0)
    negative_count = sum(1 for item in instruments if item["pct_change"] < 0)
    if avg_change >= 0.35 and positive_count >= negative_count:
        market_bias = "bullish"
    elif avg_change <= -0.35 and negative_count >= positive_count:
        market_bias = "bearish"
    else:
        market_bias = "mixed"
    leaders = sorted(instruments, key=lambda item: item["pct_change"], reverse=True)[:2]
    laggards = sorted(instruments, key=lambda item: item["pct_change"])[:2]
    payload = {
        "summary": f"Market breadth is {market_bias} with an average move of {avg_change:+.2f}% across the tracked instruments.",
        "market_bias": market_bias,
        "avg_change": avg_change,
        "instruments": instruments,
        "leaders": leaders,
        "laggards": laggards,
    }
    _market_cache["payload"] = payload
    _market_cache["expires_at"] = now + MARKET_CACHE_TTL
    return payload
