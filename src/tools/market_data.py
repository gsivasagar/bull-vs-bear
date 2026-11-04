import logging
from typing import Any, Dict

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
