import logging
import re
from typing import Dict, List

from duckduckgo_search import DDGS

from src import config
from src.cache import ttl_cache

log = logging.getLogger(__name__)

_TAGS = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")


def clean(text: object, limit: int) -> str:
    """Plain, single-line, length-limited text. News comes from the open web, so treat it as untrusted."""
    text = _SPACE.sub(" ", _TAGS.sub(" ", str(text or ""))).strip()
    return text[:limit]


def _safe_url(url: object) -> str:
    url = str(url or "").strip()
    return url if url.lower().startswith(("http://", "https://")) else ""


@ttl_cache(lambda: config.DATA_CACHE_TTL_SECONDS)
def get_market_news(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Recent headlines for the query. Returns an empty list on failure: news is helpful, not essential."""
    try:
        results = DDGS().news(keywords=query, max_results=max_results) or []
    except Exception as exc:
        log.warning("News lookup failed: %s", exc)
        return []
    return [{
        "title": clean(r.get("title"), 200),
        "summary": clean(r.get("body"), 400),
        "source": clean(r.get("source"), 80),
        "url": _safe_url(r.get("url")),
        "date": clean(r.get("date"), 40),
    } for r in results if isinstance(r, dict)]
