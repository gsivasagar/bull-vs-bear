"""Structured verdict, token usage, cancellation, proxy-aware client address, demo mode, news tidying."""
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src import api, config
from src.agents import nodes
from src.cancel import Cancelled, new_event, run_config
from src.demo import DemoCaps
from src.graph import create_graph
from src.tools import news
from src.verdict import JudgeVerdict, render_memo
from tests.conftest import FakeLLM


def state(**extra):
    return {"ticker": "NVDA", "api_key": "k" * 20, "price_data": {}, "financials": {}, "quant": {}, "news_data": [],
            "bull_argument": "", "bear_argument": "", "verdict": "", "recommendation": "", "judge": {}, "usage": [],
            **extra}


# ---- D1 structured verdict --------------------------------------------------------------------------------------
def test_structured_verdict_drives_the_label_and_the_memo(client):
    body = client.post("/api/debate", json={"ticker": "NVDA"}, headers={"X-Api-Key": "k" * 20}).json()
    assert body["recommendation"] == "BUY"
    assert body["judge"]["confidence"] == "medium" and body["judge"]["cited_figures"] == ["123.45"]
    assert "**Verdict**: BUY (confidence: medium)" in body["verdict"]        # memo is built from the fields


def test_falls_back_to_the_text_memo_when_the_model_has_no_structured_output(client, monkeypatch, calls):
    monkeypatch.setattr(nodes, "get_llm", lambda k, t, m=None: FakeLLM(log=calls, structured=False))
    body = client.post("/api/debate", json={"ticker": "NVDA"}, headers={"X-Api-Key": "k" * 20}).json()
    assert body["recommendation"] == "BUY" and body["judge"] == {}


def test_a_structured_answer_that_does_not_fit_the_schema_falls_back_to_text(client, monkeypatch, calls):
    class Bad(FakeLLM):
        def with_structured_output(self, schema, include_raw=False):
            outer = self
            return SimpleNamespace(invoke=lambda msgs: {"raw": outer.invoke(msgs), "parsed": None,
                                                        "parsing_error": ValueError("bad")})

    monkeypatch.setattr(nodes, "get_llm", lambda k, t, m=None: Bad(log=calls))
    body = client.post("/api/debate", json={"ticker": "NVDA"}, headers={"X-Api-Key": "k" * 20}).json()
    assert body["recommendation"] == "BUY" and body["judge"] == {}


def test_schema_rejects_a_label_outside_buy_sell_hold():
    with pytest.raises(ValueError):
        JudgeVerdict(recommendation="MAYBE", confidence="low", key_reasons=["x"], risks=[], conclusion="c")
    memo = render_memo(JudgeVerdict(recommendation="SELL", confidence="high", key_reasons=["a"], risks=[], conclusion="c"))
    assert memo.startswith("**Verdict**: SELL") and "None stated" in memo


# ---- D4 position bias switch ------------------------------------------------------------------------------------
@pytest.mark.parametrize("order,first,second", [("bull_first", "BULL ARGUMENT", "BEAR ARGUMENT"),
                                                ("bear_first", "BEAR ARGUMENT", "BULL ARGUMENT")])
def test_the_judge_reads_the_arguments_in_the_requested_order(calls, order, first, second):
    out = create_graph().invoke(state(judge_order=order))
    human = next(c for c in calls if c["role"] == "judge")["human"]
    assert human.index(first) < human.index(second) and out["recommendation"] == "BUY"


# ---- E4 usage ---------------------------------------------------------------------------------------------------
def test_usage_adds_up_every_model_call(client):
    body = client.post("/api/debate", json={"ticker": "NVDA"}, headers={"X-Api-Key": "k" * 20}).json()
    assert body["usage"] == {"calls": 3, "input_tokens": 300, "output_tokens": 60, "cost_usd": None}


def test_cost_is_shown_only_when_prices_are_configured(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_INPUT_USD_PER_M", "0.10")
    monkeypatch.setattr(config, "GEMINI_OUTPUT_USD_PER_M", "0.40")
    got = api.summarize_usage([{"input_tokens": 1_000_000, "output_tokens": 500_000}])
    assert got["cost_usd"] == pytest.approx(0.30)
    monkeypatch.setattr(config, "GEMINI_OUTPUT_USD_PER_M", "oops")
    assert api.summarize_usage([{"input_tokens": 1, "output_tokens": 1}])["cost_usd"] is None


def test_the_stream_reports_usage_in_the_final_event(client):
    import json
    r = client.post("/api/debate/stream", json={"ticker": "NVDA"}, headers={"X-Api-Key": "k" * 20})
    blocks = [b for b in r.text.split("\n\n") if b.startswith("event: done")]
    final = json.loads(blocks[0].split("data: ", 1)[1])
    assert final["usage"]["calls"] == 3 and final["judge"]["recommendation"] == "BUY"


# ---- E2 cancellation --------------------------------------------------------------------------------------------
def test_a_cancelled_debate_makes_no_model_calls(calls):
    event = new_event()
    event.set()
    with pytest.raises(Cancelled):
        create_graph().invoke(state(ticker="NVDA"), config=run_config(event))
    assert calls == []


def test_leaving_between_steps_skips_the_judge(monkeypatch, calls):
    event = threading.Event()
    real = nodes.bear_agent_node

    def bear_then_leave(s, config):
        out = real(s, config)
        event.set()                         # the visitor closes the tab while the debate is running
        return out

    monkeypatch.setattr("src.graph.bear_agent_node", bear_then_leave)
    with pytest.raises(Cancelled):
        create_graph().invoke(state(), config=run_config(event))
    assert "judge" not in {c["role"] for c in calls}


# ---- E1 client address ------------------------------------------------------------------------------------------
def fake_request(forwarded=None, host="10.0.0.9"):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_without_a_trusted_proxy_the_header_is_ignored(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 0)
    assert api.client_ip(fake_request("1.2.3.4")) == "10.0.0.9"


def test_behind_one_proxy_the_last_entry_is_used_and_forged_ones_are_not(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 1)
    assert api.client_ip(fake_request("6.6.6.6, 203.0.113.7")) == "203.0.113.7"   # 6.6.6.6 was sent by the visitor
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 2)
    assert api.client_ip(fake_request("6.6.6.6, 203.0.113.7, 10.1.1.1")) == "203.0.113.7"


def test_a_missing_or_short_header_falls_back_to_the_socket(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 2)
    assert api.client_ip(fake_request(None)) == "10.0.0.9"
    assert api.client_ip(fake_request("1.1.1.1")) == "10.0.0.9"


# ---- E3 demo mode -----------------------------------------------------------------------------------------------
def test_caps_per_visitor_and_in_total_and_reset_each_day():
    day = ["2026-01-01"]
    caps = DemoCaps(per_visitor=2, total=3, today=lambda: day[0])
    assert caps.take("a") is None and caps.take("a") is None
    assert "2 free demo" in caps.take("a")
    assert caps.take("b") is None
    assert "today's limit" in caps.take("c")                       # 3 used overall
    day[0] = "2026-01-02"
    assert caps.take("a") is None                                  # a new day starts fresh


def test_refund_gives_a_run_back():
    caps = DemoCaps(per_visitor=1, total=5)
    assert caps.take("a") is None and caps.take("a") is not None
    caps.refund("a")
    assert caps.take("a") is None


def test_demo_off_by_default_and_the_config_endpoint_says_so(client):
    assert config.DEMO_API_KEY == ""
    assert client.get("/api/config").json()["demo_enabled"] is False


def test_demo_uses_the_server_key_and_model_but_a_visitor_key_wins(client, monkeypatch, seen_keys):
    monkeypatch.setattr(config, "DEMO_API_KEY", "server-demo-key")
    monkeypatch.setattr(config, "DEMO_MODEL", "cheap-model")
    monkeypatch.setattr(api, "_demo", DemoCaps(2, 10))
    assert client.get("/api/config").json()["demo_enabled"] is True
    r = client.post("/api/debate", json={"ticker": "NVDA"})
    assert r.status_code == 200 and "server-demo-key" in seen_keys
    assert "server-demo-key" not in r.text                                   # never sent to the browser
    seen_keys.clear()
    client.post("/api/debate", json={"ticker": "NVDA"}, headers={"X-Api-Key": "v" * 20})
    assert set(seen_keys) == {"v" * 20}


def test_demo_cap_returns_429_with_a_plain_message(client, monkeypatch):
    monkeypatch.setattr(config, "DEMO_API_KEY", "server-demo-key")
    monkeypatch.setattr(api, "_demo", DemoCaps(1, 10))
    assert client.post("/api/debate", json={"ticker": "NVDA"}).status_code == 200
    r = client.post("/api/debate", json={"ticker": "NVDA"})
    assert r.status_code == 429 and "own Gemini API key" in r.json()["detail"]


def test_a_failed_lookup_does_not_use_up_a_demo_run(client, monkeypatch):
    monkeypatch.setattr(config, "DEMO_API_KEY", "server-demo-key")
    caps = DemoCaps(1, 10)
    monkeypatch.setattr(api, "_demo", caps)
    monkeypatch.setattr(nodes, "get_stock_price", lambda t: {"error": "x", "kind": "not_found"})
    assert client.post("/api/debate", json={"ticker": "ZZZZ"}).status_code == 404
    monkeypatch.setattr(nodes, "get_stock_price", lambda t: {"ticker": t, "current_price": 1.0, "currency": "USD"})
    assert client.post("/api/debate", json={"ticker": "NVDA"}).status_code == 200


# ---- D7 news ----------------------------------------------------------------------------------------------------
NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


def item(title, date):
    return {"title": title, "summary": "", "source": "s", "url": "", "date": date}


def test_tidy_drops_old_and_repeated_items_and_keeps_undated_ones():
    items = [item("Ford recalls trucks", "2026-11-08T10:00:00+00:00"),
             item("FORD recalls  trucks!", "2026-11-08T11:00:00+00:00"),          # same headline, syndicated
             item("Old story", "2026-08-01T00:00:00+00:00"),
             item("No date here", ""), item("Bad date", "yesterday-ish"), item("", "2026-11-08T00:00:00+00:00")]
    got = [i["title"] for i in news.tidy(items, 5, now=NOW)]
    assert got == ["Ford recalls trucks", "No date here", "Bad date"]


def test_tidy_respects_the_limit():
    assert len(news.tidy([item(f"t{i}", "") for i in range(9)], 5, now=NOW)) == 5


def test_the_query_uses_the_company_name_for_short_tickers():
    assert nodes.news_query("F", "Ford Motor Company") == "Ford Motor Company F stock news"
    assert nodes.news_query("NVDA", None) == "NVDA stock news"
    assert nodes.news_query("NVDA", "NVDA") == "NVDA stock news"


# ---- E3 saved examples ------------------------------------------------------------------------------------------
def test_examples_are_listed_and_served_from_the_folder(client, monkeypatch, tmp_path):
    import json
    (tmp_path / "NVDA.json").write_text(json.dumps({"ticker": "NVDA", "recommendation": "HOLD", "saved_on": "2026-11-09"}))
    (tmp_path / "bad name.json").write_text("{}")                 # not a ticker: never served
    (tmp_path / "BROKEN.json").write_text("not json")
    monkeypatch.setattr(config, "EXAMPLES_DIR", tmp_path)
    assert client.get("/api/examples").json() == [{"ticker": "NVDA", "recommendation": "HOLD", "saved_on": "2026-11-09"}]
    assert client.get("/api/examples/nvda").json()["recommendation"] == "HOLD"
    assert client.get("/api/examples/ZZZZ").status_code == 404
    assert client.get("/api/examples/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_no_examples_folder_means_an_empty_list(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "EXAMPLES_DIR", tmp_path / "missing")
    assert client.get("/api/examples").json() == []
