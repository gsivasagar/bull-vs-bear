import yfinance as yf
from typing import Dict, Any

def get_stock_price(ticker: str) -> Dict[str, Any]:
    """
    Fetches the current stock price and basic info for a given ticker.
    """
    try:
        stock = yf.Ticker(ticker)
        # fast_info is often faster for current price
        history = stock.history(period="1d")
        if history.empty:
            return {"error": f"No data found for ticker {ticker}"}
        
        current_price = history['Close'].iloc[-1]
        info = stock.info
        
        return {
            "ticker": ticker,
            "current_price": current_price,
            "currency": info.get("currency", "USD"),
            "company_name": info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "summary": info.get("longBusinessSummary", "No summary available.")
        }
    except Exception as e:
        return {"error": str(e)}

def get_financials(ticker: str) -> Dict[str, Any]:
    """
    Fetches key financial ratios and data.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        return {
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "dividend_yield": info.get("dividendYield"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins")
        }
    except Exception as e:
        return {"error": str(e)}
