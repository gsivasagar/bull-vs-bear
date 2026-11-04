import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src import api
from src.ratelimit import RateLimiter

PRICE = {"ticker": "NVDA", "current_price": 123.45, "currency": "USD", "company_name": "NVIDIA", "sector": "Tech",
         "summary": "Makes chips."}
FINANCIALS = {"market_cap": 3_000_000_000_000, "pe_ratio": 60.1}
NEWS = [{"title": "NVDA beats", "summary": "Strong quarter", "source": "Wire", "url": "https://example.com/a", "date": "today"}]


class FakeLLM:
    """Stands in for a chat model: records every call, can sleep, and can be told to fail."""

    def __init__(self, label="x", delay=0.0, error=None, log=None, fail_roles=None):
        self.label, self.delay, self.error, self.log = label, delay, error, log if log is not None else []
        self.fail_roles = fail_roles          # None: fail every role (when error is set); else only these roles

    def invoke(self, messages):
        start = time.monotonic()
        if self.delay:
            time.sleep(self.delay)
        system, human = messages[0].content, messages[1].content
        role = "judge" if "Judge" in system else "bull" if "Bull" in system else "bear"
        if self.error and (self.fail_roles is None or role in self.fail_roles):
            raise self.error
        self.log.append({"role": role, "human": human, "thread": threading.get_ident(),
                         "start": start, "end": time.monotonic()})
        text = {"bull": "Bull case: growth.", "bear": "Bear case: valuation.",
                "judge": "BUY\n**Verdict**: BUY\nRationale."}[role]
        return SimpleNamespace(content=text)


@pytest.fixture
def calls():
    return []


@pytest.fixture(autouse=True)
def isolate(monkeypatch, calls):
    """No network, a fresh rate limiter, and fake data/LLM by default. Tests override pieces as needed."""
    from src.agents import nodes
    from src.tools import market_data, news

    for fn in (market_data.get_stock_price, market_data.get_financials, news.get_market_news):
        fn.cache_clear()
    monkeypatch.setattr(nodes, "get_stock_price", lambda t: dict(PRICE, ticker=t))
    monkeypatch.setattr(nodes, "get_financials", lambda t: dict(FINANCIALS))
    monkeypatch.setattr(nodes, "get_market_news", lambda q: [dict(n) for n in NEWS])
    seen_keys = []
    monkeypatch.setattr(nodes, "get_llm", lambda key, temp: (seen_keys.append(key), FakeLLM(log=calls))[1])
    monkeypatch.setattr(api, "_limiter", RateLimiter(1000))
    api.get_graph.cache_clear()
    return seen_keys


@pytest.fixture
def seen_keys(isolate):
    return isolate


@pytest.fixture
def client():
    return TestClient(api.app, raise_server_exceptions=False)
