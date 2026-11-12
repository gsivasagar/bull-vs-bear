import json

import pytest

from src import api
from src.agents import nodes
from src.ratelimit import RateLimiter
from tests.conftest import FakeLLM

KEY = "AIzaSyD-this-is-a-fake-key-0123456789abcd"


def post(client, ticker="nvda", key=None, **extra):
    headers = {"X-Api-Key": key} if key else {}
    return client.post("/api/debate", json={"ticker": ticker, **extra}, headers=headers)


def test_happy_path_returns_the_expected_whitelisted_shape(client):
    r = post(client)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"ticker", "price_data", "financials", "quant", "news", "bull_argument", "bear_argument", "verdict",
                         "recommendation", "judge", "usage", "disclaimer"}
    assert body["ticker"] == "NVDA" and body["recommendation"] == "BUY"
    assert set(body["price_data"]) == {"company_name", "current_price", "currency", "sector"}
    assert "not financial advice" in body["disclaimer"]


def test_the_browser_gets_the_full_quant_block_with_a_version(client):
    quant = post(client).json()["quant"]
    assert quant["schema_version"] == 1 and quant["track_record"]["scores"] and quant["price"]["past_months_up_pct"] is not None


def test_the_api_key_is_used_but_never_returned(client, seen_keys):
    r = post(client, key=KEY)
    assert r.status_code == 200
    assert KEY not in r.text and "api_key" not in r.text
    assert set(seen_keys) == {KEY}


def test_a_key_in_the_body_is_ignored(client, seen_keys):
    r = post(client, api_key=KEY)
    assert r.status_code == 200 and KEY not in r.text
    assert set(seen_keys) == {None}


def test_no_key_means_local_model(client, seen_keys):
    post(client)
    assert set(seen_keys) == {None}


@pytest.mark.parametrize("bad", ["", "   ", "../etc/passwd", "NVDA; DROP TABLE", "<script>", "A" * 30, "NV DA", "$$"])
def test_bad_tickers_are_rejected(client, bad, calls):
    assert post(client, ticker=bad).status_code == 422
    assert calls == []


def test_ticker_is_normalised(client):
    assert post(client, ticker=" brk.b ").json()["ticker"] == "BRK.B"


@pytest.mark.parametrize("key", ["has space in it", "x" * 300])
def test_malformed_keys_are_rejected(client, key):
    assert post(client, key=key).status_code == 400


def test_error_statuses_and_no_internal_details(client, monkeypatch, calls):
    monkeypatch.setattr(nodes, "get_stock_price", lambda t: {"error": "x", "kind": "not_found"})
    r = post(client, ticker="ZZZZ")
    assert r.status_code == 404 and "ZZZZ" in r.json()["detail"]

    monkeypatch.setattr(nodes, "get_stock_price", lambda t: {"price": 1})
    for err, status in ((ConnectionError("refused 10.0.0.5"), 503), (Exception("429 quota"), 429),
                        (Exception("400 INVALID_ARGUMENT API key not valid"), 401),
                        (ValueError("secret internal detail"), 502)):
        monkeypatch.setattr(nodes, "get_llm", lambda k, t, m=None, e=err: FakeLLM(error=e))
        monkeypatch.setattr("src.llm.time.sleep", lambda s: None)
        monkeypatch.setattr("src.config.LLM_MAX_RETRIES", 0)
        r = post(client)
        assert r.status_code == status
        assert "secret" not in r.text and "10.0.0.5" not in r.text


def test_unexpected_errors_are_a_generic_500(client, monkeypatch):
    def boom(t):
        raise RuntimeError("secret stack detail")

    monkeypatch.setattr(nodes, "get_stock_price", boom)
    r = post(client)
    assert r.status_code == 500 and "secret" not in r.text


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(api, "_limiter", RateLimiter(2))
    assert [post(client).status_code for _ in range(3)] == [200, 200, 429]
    assert post(client).headers["retry-after"] == "60"


def test_cors_allows_the_configured_origin_only_and_no_credentials(client):
    ok = client.options("/api/debate", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "x-api-key,content-type"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in ok.headers
    bad = client.options("/api/debate", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_search_and_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/search?q=").json() == []
    hits = client.get("/api/search?q=nvid").json()
    assert hits and hits[0]["symbol"] == "NVDA" and len(client.get("/api/search?q=a").json()) <= 10
    assert client.get("/api/search?q=" + "a" * 50).status_code == 422


# ---------- streaming ----------
def events(response):
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_stream_sends_progress_then_the_final_result(client, seen_keys):
    r = client.post("/api/debate/stream", json={"ticker": "nvda"}, headers={"X-Api-Key": KEY})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = events(r)
    names = [n for n, _ in ev]
    assert names[0] == "start" and names[-1] == "done"
    stages = [d["stage"] for n, d in ev if n == "stage"]
    assert stages[0] == "fetch_data" and stages[-1] == "judge_agent" and set(stages[1:3]) == {"bull_agent", "bear_agent"}
    final = ev[-1][1]
    assert final["recommendation"] == "BUY" and final["bull_argument"] and final["bear_argument"]
    assert KEY not in r.text and "api_key" not in r.text
    first_stage = [d for n, d in ev if n == "stage"][0]["result"]
    assert first_stage["price_data"]["current_price"] == 123.45 and first_stage["verdict"] == ""   # partial result


def test_stream_reports_errors_as_an_event(client, monkeypatch):
    monkeypatch.setattr(nodes, "get_stock_price", lambda t: {"error": "x", "kind": "not_found"})
    ev = events(client.post("/api/debate/stream", json={"ticker": "ZZZZ"}))
    assert ev[-1][0] == "error" and ev[-1][1]["status"] == 404 and "ZZZZ" in ev[-1][1]["detail"]


def test_stream_hides_unexpected_errors(client, monkeypatch):
    monkeypatch.setattr(nodes, "get_stock_price", lambda t: (_ for _ in ()).throw(RuntimeError("secret stack detail")))
    r = client.post("/api/debate/stream", json={"ticker": "NVDA"})
    assert events(r)[-1] == ("error", {"status": 500, "detail": "Something went wrong while running the debate."})
    assert "secret" not in r.text


def test_stream_validates_and_rate_limits_before_starting(client, monkeypatch):
    assert client.post("/api/debate/stream", json={"ticker": "<x>"}).status_code == 422
    monkeypatch.setattr(api, "_limiter", RateLimiter(0))
    assert client.post("/api/debate/stream", json={"ticker": "NVDA"}).status_code == 429
