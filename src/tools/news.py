import logging
import re
from datetime import datetime, timedelta, timezone
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


def _age_ok(date_text: str, now: datetime, max_age_days: int) -> bool:
    """False only when the item has a readable date older than the limit; undated items are kept."""
    try:
        when = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return now - when <= timedelta(days=max_age_days)


def tidy(items: List[Dict[str, str]], limit: int, now: datetime | None = None, max_age_days: int = 30
         ) -> List[Dict[str, str]]:
    """Drop old items and repeated headlines (syndicated stories), keep the first `limit`."""
    now = now or datetime.now(timezone.utc)
    seen, kept = set(), []
    for item in items:
        key = re.sub(r"\W+", " ", item.get("title", "").lower()).strip()
        if not key or key in seen or not _age_ok(item.get("date", ""), now, max_age_days):
            continue
        seen.add(key)
        kept.append(item)
    return kept[:limit]


@ttl_cache(lambda: config.DATA_CACHE_TTL_SECONDS)
def get_market_news(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Recent headlines for the query. Returns an empty list on failure: news is helpful, not essential."""
    try:
        results = DDGS().news(keywords=query, max_results=max_results * 3) or []
    except Exception as exc:
        log.warning("News lookup failed: %s", exc)
        return []
    items = [{
        "title": clean(r.get("title"), 200),
        "summary": clean(r.get("body"), 400),
        "source": clean(r.get("source"), 80),
        "url": _safe_url(r.get("url")),
        "date": clean(r.get("date"), 40),
    } for r in results if isinstance(r, dict)]
    return tidy(items, max_results)
