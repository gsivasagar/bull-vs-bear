import json
import logging

import numpy as np
import pytest

from src import config
from src.tools import market_data, quant


def garch_series(n=1260, seed=7, w=2e-6, a=0.09, b=0.89):
    """Daily log returns with volatility clustering, from a known GARCH(1,1) process."""
    rng = np.random.default_rng(seed)
    r, v = np.zeros(n), w / (1 - a - b)
    for i in range(n):
        r[i] = np.sqrt(v) * rng.standard_normal()
        v = w + a * r[i] ** 2 + b * v
    return r


def closes_from(returns):
    return (100 * np.exp(np.cumsum(returns))).tolist()


def dates_for(n):
    return [f"d{i:05d}" for i in range(n)]


@pytest.fixture(scope="module")
def closes():
    return closes_from(garch_series())


@pytest.fixture(scope="module")
def block(closes):
    return quant.analyze(closes, dates_for(len(closes)), model="long_run")


# ---- basic maths ------------------------------------------------------------------------------------------------

def test_log_returns_and_input_checks():
    assert quant.log_returns([100, 110]).tolist() == pytest.approx([np.log(1.1)])
    for bad in ([100], [100, 0, 90], [100, -1], [100, float("nan")], [[1, 2], [3, 4]]):
        with pytest.raises(ValueError):
            quant.log_returns(bad)


def test_annualize_known_value():
    assert quant.annualize(0.01 ** 2) == pytest.approx(0.01 * np.sqrt(252) * 100)
    assert quant.annualize(-1.0) == 0.0                                  # never a NaN from a negative variance


def test_qlike_is_zero_for_a_perfect_forecast_and_punishes_under_forecasting_more():
    assert quant.qlike(4.0, 4.0) == pytest.approx(0.0)
    under, over = quant.qlike(1.0, 4.0), quant.qlike(4.0, 1.0)           # forecast too low vs too high by the same factor
    assert under > over > 0


# ---- the models -------------------------------------------------------------------------------------------------

def test_naive_uses_only_the_last_month_and_long_run_the_last_year():
    r = np.concatenate([np.full(300, 0.05), np.full(21, 0.01)])
    assert quant.forecast_naive(r, 21) == pytest.approx(0.01 ** 2)
    assert quant.forecast_long_run(r, 21) == pytest.approx(np.mean(np.square(r[-252:])))


def test_ewma_matches_a_hand_calculation():
    r = np.concatenate([np.full(21, 0.01), [0.03]])
    assert quant.forecast_ewma(r, 21) == pytest.approx(0.94 * 0.01 ** 2 + 0.06 * 0.03 ** 2)


def test_ewma_reacts_to_a_recent_shock_more_than_long_run_does():
    r = np.concatenate([np.full(300, 0.005), np.full(5, 0.06)])
    assert quant.forecast_ewma(r, 21) > quant.forecast_long_run(r, 21)


@pytest.mark.parametrize("name", ["garch", "garch_t", "gjr"])
def test_garch_family_forecasts_are_positive_and_near_the_truth(name):
    f = quant.OFFLINE_FORECASTERS[name](garch_series(), 21)
    long_run_true = 2e-6 / (1 - 0.09 - 0.89)                              # the process's long-run daily variance
    assert 0.2 * long_run_true < f < 5 * long_run_true


def test_the_request_path_models_need_no_extra_packages():
    assert set(quant.FORECASTERS) == {"naive", "long_run", "ewma"}


# ---- no peeking at the future, and reproducibility --------------------------------------------------------------

def test_forecasts_do_not_depend_on_data_after_the_forecast_date():
    r = garch_series(800)
    t = 600
    base = quant.forecasts_at(r, t, forecasters=quant.OFFLINE_FORECASTERS)
    changed = r.copy()
    changed[t:] = changed[t:] * 10 + 0.05                                 # wreck everything after the forecast date
    assert quant.forecasts_at(changed, t, forecasters=quant.OFFLINE_FORECASTERS) == base


def test_garch_forecast_is_reproducible_to_four_decimals():
    r = garch_series(900)
    first, second = quant.forecast_garch(r, 21), quant.forecast_garch(r, 21)
    assert quant.annualize(first) == pytest.approx(quant.annualize(second), abs=1e-4)


def test_the_whole_block_is_reproducible(closes):
    a = quant.analyze(closes, dates_for(len(closes)), model="long_run")
    b = quant.analyze(closes, dates_for(len(closes)), model="long_run")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_walk_forward_covers_the_expected_dates():
    r = garch_series(700)
    records, skipped = quant.walk_forward_records(r, dates_for(701))
    assert len(records) + skipped == len(range(504, 700 - 21 + 1, 21))
    assert records[0]["date"] == "d00504"                                  # the forecast is dated at the last known price


def test_a_failed_model_drops_that_date_for_every_model(monkeypatch):
    calls = {"n": 0}
    real = quant.forecast_ewma

    def flaky(returns, horizon):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise RuntimeError("boom")
        return real(returns, horizon)

    monkeypatch.setitem(quant.FORECASTERS, "ewma", flaky)
    records, skipped = quant.walk_forward_records(garch_series(800))
    assert skipped > 0 and records
    assert all(set(r["forecasts"]) == {"naive", "long_run", "ewma"} for r in records)


def test_calibration_is_close_to_normal_for_a_known_process():
    # Simulated returns with constant volatility: about 68% of 21-day moves should be inside +-1 sigma.
    rng = np.random.default_rng(3)
    r = 0.01 * rng.standard_normal(6000)
    records, _ = quant.walk_forward_records(r)
    scores = quant.score_records(records, ["long_run"])
    assert 60 <= scores["long_run"]["inside_1sigma_pct"] <= 76
    assert 90 <= scores["long_run"]["inside_2sigma_pct"] <= 99


# ---- the block --------------------------------------------------------------------------------------------------

def test_block_shape(block):
    assert block["schema_version"] == quant.SCHEMA_VERSION == 1
    v, t = block["volatility"], block["track_record"]
    assert v["model"] == "long_run" and v["fallback_used"] is False and v["forecast_annualized_pct"] > 0
    assert v["regime"] in ("low", "normal", "high") and 0 <= v["percentile_1y"] <= 100
    assert t["status"] == "ready" and t["test_dates"] > 20
    assert set(t["scores"]) == {"naive", "long_run", "ewma"}
    assert set(t["calibration"]) == {"inside_1sigma_pct", "inside_2sigma_pct"}
    assert "direction" not in block and "not which way" in block["caveats"][0]
    assert block["as_of"] == "d01259"                                      # the date of the last close
    json.dumps(block)                                                     # no numpy types or NaN left in it


def test_one_sigma_move_follows_from_the_forecast(block):
    v = block["volatility"]
    assert v["one_sigma_move_over_horizon_pct"] == pytest.approx(v["forecast_annualized_pct"] * np.sqrt(21 / 252), abs=0.1)


def test_the_configured_default_is_used(closes):
    out = quant.analyze(closes, dates_for(len(closes)), model="ewma")
    assert out["volatility"]["model"] == "ewma" and "recent-weighted" in out["track_record"]["summary"]


def test_default_comes_from_config_when_not_given(closes, monkeypatch):
    monkeypatch.setattr(config, "QUANT_DEFAULT_MODEL", "naive")
    assert quant.analyze(closes)["volatility"]["model"] == "naive"


def test_an_unknown_default_falls_back_to_the_one_year_average(closes):
    out = quant.analyze(closes, model="nonsense")
    assert out["volatility"]["model"] == "long_run"


def test_a_failing_model_falls_back_and_says_so(closes, monkeypatch):
    monkeypatch.setitem(quant.OFFLINE_FORECASTERS, "garch", lambda r, h: (_ for _ in ()).throw(RuntimeError("no fit")))
    out = quant.analyze(closes, dates_for(len(closes)), model="garch")
    assert out["volatility"]["model"] == "long_run" and out["volatility"]["fallback_used"] is True
    assert out["track_record"]["summary"].startswith("The usual method failed today")
    assert out["track_record"]["status"] == "ready"                       # scored for the model actually used


def test_too_little_history_is_a_clear_error_not_a_crash():
    out = quant.analyze(closes_from(garch_series(300)))
    assert out["kind"] == "insufficient_data" and "error" in out


def test_unusable_prices_are_reported():
    assert quant.analyze([100, 0, 50])["kind"] == "bad_data"


def test_a_short_record_is_reported_as_unavailable_not_invented():
    out = quant.analyze(closes_from(garch_series(570)), model="long_run")      # only a couple of test dates fit
    assert out["track_record"]["status"] == "unavailable" and out["track_record"]["scores"] == {}
    assert "Too little history" in out["track_record"]["summary"]


def test_price_context_values():
    closes = np.array([100.0] * 200 + [110.0] * 60 + [99.0])
    p = quant.price_context(closes)
    assert p["max_drawdown_1y_pct"] == pytest.approx(-10.0)
    assert p["return_1m_pct"] == pytest.approx(-10.0)
    assert p["past_months_up_note"] == "past base rate, not a forecast"


# ---- the summary sentence ---------------------------------------------------------------------------------------

def track(naive, chosen, inside=68.0, status="ready", dates=30, model="long_run"):
    scores = {"naive": {"qlike": naive}, model: {"qlike": chosen, "inside_1sigma_pct": inside}}
    return {"status": status, "test_dates": dates, "scores": scores}


def test_summary_when_the_method_beat_the_naive_guess():
    s = quant.summary_sentence("long_run", False, track(0.4, 0.2))
    assert "50% lower error than the naive guess" in s and "68% of months" in s


def test_summary_when_it_did_not_beat_the_naive_guess():
    assert "did not beat the naive guess" in quant.summary_sentence("long_run", False, track(0.2, 0.3))


def test_summary_when_there_is_too_little_history():
    assert "Too little history (5 months)" in quant.summary_sentence("long_run", False, {"status": "unavailable", "test_dates": 5})


def test_summary_when_the_method_is_the_naive_guess_itself():
    assert "nothing to beat" in quant.summary_sentence("naive", False, track(0.4, 0.4, model="naive"))


# ---- the two views ----------------------------------------------------------------------------------------------

def test_agent_view_has_no_scores_no_base_rate_and_no_direction(block):
    view = quant.agent_view(block)
    text = json.dumps(view)
    for forbidden in ("qlike", "rmse", "inside_", "past_months_up", "scores"):
        assert forbidden not in text
    assert "direction" not in view and "direction" not in view["volatility"]        # no direction field of any kind
    assert view["volatility"]["forecast_annualized_pct"] == block["volatility"]["forecast_annualized_pct"]
    assert view["summary"] == block["track_record"]["summary"] and "not which way" in view["note"]


def test_agent_view_is_small(block):
    assert len(json.dumps(quant.agent_view(block))) < 1200               # roughly 300 tokens at most


def test_ui_block_keeps_the_base_rate_with_its_label(block):
    assert block["price"]["past_months_up_pct"] is not None and "not a forecast" in block["price"]["past_months_up_note"]


def test_agent_view_of_nothing_is_nothing():
    assert quant.agent_view({}) == {}


# ---- the data wrapper -------------------------------------------------------------------------------------------

def test_get_quant_signals_passes_through_a_data_error(monkeypatch):
    quant.get_quant_signals.cache_clear()
    monkeypatch.setattr(market_data, "get_price_history", lambda t: {"error": "x", "kind": "failed"})
    assert quant.get_quant_signals("AAA")["kind"] == "failed"


def test_get_quant_signals_uses_the_history_and_logs_one_line(monkeypatch, caplog, closes):
    quant.get_quant_signals.cache_clear()
    monkeypatch.setattr(market_data, "get_price_history", lambda t: {"dates": dates_for(len(closes)), "closes": closes})
    with caplog.at_level(logging.INFO, logger="src.tools.quant"):
        out = quant.get_quant_signals("BBB")
    assert out["volatility"]["model"] == "long_run"
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("quant ticker=BBB"))
    assert "model=long_run" in line and "fallback=False" in line and "track_record=ready" in line and " ms=" in line


def test_get_quant_signals_does_not_fetch_when_switched_off(monkeypatch):
    quant.get_quant_signals.cache_clear()
    monkeypatch.setattr(config, "QUANT_ENABLED", False)
    monkeypatch.setattr(market_data, "get_price_history", lambda t: pytest.fail("must not be called"))
    assert quant.get_quant_signals("CCC")["kind"] == "disabled"


def test_get_quant_signals_is_cached(monkeypatch, closes):
    quant.get_quant_signals.cache_clear()
    n = {"calls": 0}

    def history(t):
        n["calls"] += 1
        return {"dates": dates_for(len(closes)), "closes": closes}

    monkeypatch.setattr(market_data, "get_price_history", history)
    quant.get_quant_signals("DDD"), quant.get_quant_signals("DDD")
    assert n["calls"] == 1
