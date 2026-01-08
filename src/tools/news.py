from duckduckgo_search import DDGS
from typing import List, Dict

def get_market_news(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Searches for news related to the query/ticker using DuckDuckGo.
    """
    try:
        results = DDGS().news(keywords=query, max_results=max_results)
        # DDGS news returns a list of dictionaries with 'title', 'body', 'url', 'date', 'source'
        news_items = []
        if results:
            for result in results:
                news_items.append({
                    "title": result.get("title", ""),
                    "summary": result.get("body", ""),
                    "source": result.get("source", ""),
                    "url": result.get("url", ""),
                    "date": result.get("date", "")
                })
        return news_items
    except Exception as e:
        return [{"error": str(e)}]
