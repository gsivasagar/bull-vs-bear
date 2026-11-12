import logging
from datetime import datetime, time
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import yfinance as yf

from src import config
from src.cache import ttl_cache

log = logging.getLogger(__name__)


def _ttl() -> float:
    return config.DATA_CACHE_TTL_SECONDS


@ttl_cache(_ttl)
def get_stock_price(ticker: str) -> Dict[str, Any]:
    """Current price and basic company info. Returns {"error": ...} when nothing is found."""
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period="1d")
        if history.empty:
            return {"error": f"No data found for ticker {ticker}", "kind": "not_found"}
        info = stock.info or {}
        return {
            "ticker": ticker,
            "current_price": float(history["Close"].iloc[-1]),
            "currency": info.get("currency", "USD"),
            "company_name": info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "summary": info.get("longBusinessSummary", "No summary available."),
        }
    except Exception as exc:  # network problems, unknown symbols, upstream changes
        log.warning("Price lookup failed for %s: %s", ticker, exc)
        return {"error": "Market data lookup failed", "kind": "failed"}


@ttl_cache(_ttl)
def get_financials(ticker: str) -> Dict[str, Any]:
    """Key ratios. Returns {"error": ...} when the lookup fails."""
    try:
        info = yf.Ticker(ticker).info or {}
        return {
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "dividend_yield": info.get("dividendYield"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
        }
    except Exception as exc:
        log.warning("Financials lookup failed for %s: %s", ticker, exc)
        return {"error": "Financials lookup failed", "kind": "failed"}


NEW_YORK = ZoneInfo("America/New_York")
MARKET_CLOSE = time(16, 0)


def drop_unfinished_day(dates: List[str], closes: List[float], now: datetime | None = None):
    """Remove the last row when it is today's session in New York and the US market has not closed yet.

    During the session Yahoo returns a row for today whose "close" is just the latest trade. Using it would make the
    last return an unfinished day. (US listings only: for other exchanges the row is kept as is.)"""
    if not dates:
        return dates, closes
    local = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    if dates[-1] == local.date().isoformat() and local.time() < MARKET_CLOSE:
        return dates[:-1], closes[:-1]
    return dates, closes


def _history_ttl() -> float:
    return config.PRICE_HISTORY_TTL_SECONDS


@ttl_cache(_history_ttl)
def get_price_history(ticker: str, years: int = 5) -> Dict[str, Any]:
    """Daily closes for the last `years` years, oldest first, without an unfinished trading day.

    Returns {"error": ...} when nothing is found. Closes are adjusted by Yahoo for later splits and dividends."""
    try:
        history = yf.Ticker(ticker).history(period=f"{years}y")
        if history.empty:
            return {"error": f"No price history found for {ticker}", "kind": "not_found"}
        closes = history["Close"].dropna()
        dates = [d.strftime("%Y-%m-%d") for d in closes.index]
        dates, values = drop_unfinished_day(dates, [float(c) for c in closes.to_numpy()])
        if not dates:
            return {"error": f"No price history found for {ticker}", "kind": "not_found"}
        return {"dates": dates, "closes": values}
    except Exception as exc:
        log.warning("Price history lookup failed for %s: %s", ticker, exc)
        return {"error": "Price history lookup failed", "kind": "failed"}
