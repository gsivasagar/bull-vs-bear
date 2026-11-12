"""The live-evaluation script, run against the fake model so a mistake is found before real quota is spent."""
from scripts import live_eval
from src.agents import nodes
from src.graph import create_graph
from tests.conftest import FakeLLM


def test_one_run_records_verdict_usage_and_faithfulness(calls, monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda k, t, m=None: FakeLLM(log=calls))
    row = live_eval.one_run(create_graph(), "k" * 20, "NVDA", "bear_first", 2)
    assert row["recommendation"] == "BUY" and row["structured"] is True and row["order"] == "bear_first" and row["rep"] == 2
    assert row["usage"]["calls"] == 3 and set(row["faithfulness"]) == {"bull", "bear", "judge"}


def test_a_failing_model_becomes_an_error_row_not_a_crash(monkeypatch, calls):
    monkeypatch.setattr(nodes, "get_llm", lambda k, t, m=None: FakeLLM(error=ValueError("boom"), log=calls))
    row = live_eval.one_run(create_graph(), "k" * 20, "NVDA", "bull_first", 0)
    assert "error" in row and "boom" not in row["error"]


def test_write_produces_json_and_markdown(tmp_path, monkeypatch, calls):
    monkeypatch.setattr(live_eval, "OUT", tmp_path)
    monkeypatch.setattr(nodes, "get_llm", lambda k, t, m=None: FakeLLM(log=calls))
    runs = [live_eval.one_run(create_graph(), "k" * 20, "NVDA", o, 0) for o in ("bull_first", "bear_first")]
    live_eval.write(runs, "smoke")
    files = sorted(p.suffix for p in tmp_path.iterdir())
    assert files == [".json", ".md"]
    assert "Position bias" in next(p for p in tmp_path.iterdir() if p.suffix == ".md").read_text()
