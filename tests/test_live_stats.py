from src.tools import live_stats as ls


def run(ticker, rec, rep=0, order="bull_first", **kw):
    return {"ticker": ticker, "order": order, "rep": rep, "recommendation": rec, **kw}


def test_flip_rate_is_the_share_not_matching_the_most_common_verdict():
    runs = [run("A", "BUY", i) for i in range(4)] + [run("A", "SELL", 4)] + [run("B", "HOLD", i) for i in range(5)]
    out = ls.flip_rate(runs)
    assert out["per_ticker"] == {"A": 0.2, "B": 0.0} and out["mean"] == 0.1


def test_flip_rate_needs_two_good_runs_and_ignores_failures_and_the_other_order():
    runs = [run("A", "BUY"), run("A", "UNKNOWN", 1), run("A", "SELL", 2, error="x"), run("A", "SELL", 3, order="bear_first")]
    assert ls.flip_rate(runs)["tickers"] == 0


def test_order_change_rate_pairs_the_same_ticker_and_repetition():
    runs = [run("A", "BUY", 0), run("A", "BUY", 0, "bear_first"), run("A", "BUY", 1), run("A", "SELL", 1, "bear_first"),
            run("B", "HOLD", 0)]                                    # B has no partner: not counted
    out = ls.order_change_rate(runs)
    assert out == {"pairs": 2, "changed": 1, "changed_share": 0.5}
    assert ls.order_change_rate([run("A", "BUY")])["changed_share"] is None


def test_faithfulness_pools_cited_numbers():
    f = {"bull": {"checked": 4, "supported": 3}, "bear": {"checked": 6, "supported": 6}, "judge": {"checked": 0, "supported": 0}}
    out = ls.faithfulness_share([run("A", "BUY", faithfulness=f), run("A", "BUY", 1, faithfulness=f)])
    assert out["bull"]["share"] == 0.75 and out["judge"]["share"] is None and out["all"] == {"checked": 20, "supported": 18, "share": 0.9}


def test_latency_and_tokens_and_failures_are_reported():
    runs = [run("A", "BUY", i, seconds=10 + i, usage={"input_tokens": 1000, "output_tokens": 200}) for i in range(5)]
    runs.append(run("A", "BUY", 9, error="boom"))
    s = ls.summarize(runs)
    assert s["failed"] == 1 and s["cost"]["median_seconds"] == 12.0 and s["cost"]["median_input_tokens"] == 1000
    assert s["verdict_counts"] == {"BUY": 5}
