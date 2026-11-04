from types import SimpleNamespace

import pandas as pd

from src.tools import market_data, news


class FakeTicker:
    def __init__(self, symbol, history=None, info=None, boom=False):
        self.symbol, self._h, self.info, self.boom = symbol, history, info or {}, boom

    def history(self, period):
        if self.boom:
            raise RuntimeError("network down")
        return self._h


def test_price_found(monkeypatch):
    hist = pd.DataFrame({"Close": [100.0, 101.5]})
    monkeypatch.setattr(market_data.yf, "Ticker", lambda s: FakeTicker(s, hist, {"shortName": "ACME", "currency": "USD"}))
    out = market_data.get_stock_price("ACME")
    assert out["current_price"] == 101.5 and type(out["current_price"]) is float and out["company_name"] == "ACME"


def test_price_not_found_vs_failure_are_distinguished(monkeypatch):
    monkeypatch.setattr(market_data.yf, "Ticker", lambda s: FakeTicker(s, pd.DataFrame({"Close": []})))
    assert market_data.get_stock_price("ZZZZ")["kind"] == "not_found"
    market_data.get_stock_price.cache_clear()
    monkeypatch.setattr(market_data.yf, "Ticker", lambda s: FakeTicker(s, boom=True))
    out = market_data.get_stock_price("ZZZZ")
    assert out["kind"] == "failed" and "network down" not in out["error"]      # no internals leaked


def test_price_lookups_are_cached(monkeypatch):
    n = {"calls": 0}

    def ticker(s):
        n["calls"] += 1
        return FakeTicker(s, pd.DataFrame({"Close": [1.0]}))

    monkeypatch.setattr(market_data.yf, "Ticker", ticker)
    market_data.get_stock_price("A"), market_data.get_stock_price("A")
    assert n["calls"] == 1


def test_financials(monkeypatch):
    monkeypatch.setattr(market_data.yf, "Ticker", lambda s: SimpleNamespace(info={"marketCap": 5, "trailingPE": 20}))
    out = market_data.get_financials("A")
    assert out["market_cap"] == 5 and out["pe_ratio"] == 20 and out["eps"] is None
    market_data.get_financials.cache_clear()
    monkeypatch.setattr(market_data.yf, "Ticker", lambda s: (_ for _ in ()).throw(RuntimeError("x")))
    assert market_data.get_financials("A")["kind"] == "failed"


def test_news_is_cleaned_and_untrusted_text_is_neutralised(monkeypatch):
    raw = [{"title": "<b>Big</b> news\n  today", "body": "x" * 1000, "source": "S", "url": "javascript:alert(1)", "date": "d"},
           {"title": "ok", "body": "ok", "source": "S", "url": "https://example.com/a", "date": "d"}, "junk"]
    monkeypatch.setattr(news, "DDGS", lambda: SimpleNamespace(news=lambda keywords, max_results: raw))
    out = news.get_market_news("q")
    assert out[0]["title"] == "Big news today" and len(out[0]["summary"]) == 400
    assert out[0]["url"] == "" and out[1]["url"] == "https://example.com/a" and len(out) == 2


def test_news_failure_returns_empty_and_is_not_cached(monkeypatch):
    monkeypatch.setattr(news, "DDGS", lambda: SimpleNamespace(news=lambda **k: (_ for _ in ()).throw(RuntimeError("blocked"))))
    assert news.get_market_news("q") == []
    monkeypatch.setattr(news, "DDGS", lambda: SimpleNamespace(news=lambda keywords, max_results: [{"title": "t"}]))
    assert len(news.get_market_news("q")) == 1
