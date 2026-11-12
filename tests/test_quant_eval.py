import numpy as np
import pytest

from src.tools import quant, quant_eval


def rec(date, forecast_a, forecast_b, realized=0.0001, move=0.0):
    return {"date": date, "realized_var": realized, "move": move, "forecasts": {"naive": forecast_a, "garch": forecast_b}}


def test_split_by_period_keeps_a_gap_between_selection_and_heldout():
    recs = [rec(d, 1, 1) for d in ("2023-11-30", "2023-12-15", "2024-01-02", "2025-05-05")]
    parts = quant_eval.split_by_period(recs)
    assert [r["date"] for r in parts["selection"]] == ["2023-11-30"]
    assert [r["date"] for r in parts["heldout"]] == ["2024-01-02", "2025-05-05"]      # 2023-12-15 is in neither


def test_newey_west_equals_plain_variance_of_mean_with_no_lags():
    d = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert quant_eval.newey_west_variance_of_mean(d, 0) == pytest.approx(np.var(d) / 5)


def test_newey_west_grows_when_the_series_is_positively_correlated():
    smooth = np.cumsum(np.ones(40))                                  # strongly autocorrelated after centring
    assert quant_eval.newey_west_variance_of_mean(smooth, 3) > quant_eval.newey_west_variance_of_mean(smooth, 0)


def test_dm_flags_a_clear_improvement_and_not_noise():
    rng = np.random.default_rng(1)
    better = quant_eval.diebold_mariano(0.5 + 0.1 * rng.standard_normal(36))
    noise = quant_eval.diebold_mariano(0.1 * rng.standard_normal(36))
    assert better["p_value"] < 0.001 and noise["p_value"] > 0.05
    assert better["mean_diff"] > 0


def test_dm_returns_none_with_too_few_months():
    assert quant_eval.diebold_mariano(np.array([1.0, 2.0, 3.0])) is None


def test_dm_one_sided_p_is_large_when_the_model_is_worse():
    assert quant_eval.diebold_mariano(-0.5 + 0.05 * np.random.default_rng(2).standard_normal(30))["p_value"] > 0.99


def test_monthly_differences_average_over_stocks_within_a_month():
    # two stocks in 2024-01 (naive loss minus garch loss), one in 2024-02
    a = [rec("2024-01-05", 0.0004, 0.0001, realized=0.0001)]
    b = [rec("2024-01-20", 0.0002, 0.0001, realized=0.0001)]
    c = [rec("2024-02-10", 0.0001, 0.0001, realized=0.0001)]
    d = quant_eval.monthly_loss_differences({"A": a, "B": b, "C": c}, "garch", "naive")
    expected_jan = np.mean([quant.qlike(.0004, 1e-4) - quant.qlike(.0001, 1e-4),
                            quant.qlike(.0002, 1e-4) - quant.qlike(.0001, 1e-4)])
    assert len(d) == 2 and d[0] == pytest.approx(expected_jan) and d[1] == pytest.approx(0.0)


def test_median_ratio_resists_one_extreme_stock():
    q = {f"S{i}": {"naive": 1.0, "garch": 0.9} for i in range(9)}
    q["WILD"] = {"naive": 1.0, "garch": 50.0}
    assert quant_eval.median_ratio(q, "garch", "naive") == 0.9


def selection(ratio, p):
    return {"models": {m: {"median_ratio_vs_best_baseline": 1.0, "dm_vs_best_baseline": {"p_value": 0.5}}
                       for m in quant_eval.CANDIDATES} | {"garch": {"median_ratio_vs_best_baseline": ratio,
                                                                     "dm_vs_best_baseline": {"p_value": p}}}}


def test_rule_requires_both_a_big_enough_gain_and_significance():
    assert quant_eval.choose_default(selection(0.90, 0.01), "long_run")["default_model"] == "garch"
    assert quant_eval.choose_default(selection(0.97, 0.01), "long_run")["default_model"] == "long_run"   # gain too small
    assert quant_eval.choose_default(selection(0.90, 0.20), "long_run")["default_model"] == "long_run"   # not significant
    assert quant_eval.choose_default(selection(0.95, 0.049), "long_run")["default_model"] == "garch"     # edges are inclusive


def test_rule_picks_the_lowest_ratio_among_passing_candidates():
    sel = selection(0.93, 0.01)
    sel["models"]["gjr"] = {"median_ratio_vs_best_baseline": 0.88, "dm_vs_best_baseline": {"p_value": 0.02}}
    assert quant_eval.choose_default(sel, "ewma")["default_model"] == "gjr"


def test_best_baseline_is_the_one_with_lowest_median_ratio_to_naive():
    q = {f"S{i}": {"naive": 1.0, "long_run": 0.6, "ewma": 0.8} for i in range(5)}
    assert quant_eval.best_baseline(q) == "long_run"


def test_calibration_counts_moves_inside_the_band():
    # sigma = sqrt(forecast * 21); with forecast 1/21 sigma is 1, so moves 0.5 and 1.5 -> one inside 1 sigma, both inside 2
    recs = {"A": [rec("2024-01-05", 1 / 21, 1 / 21, move=0.5), rec("2024-02-05", 1 / 21, 1 / 21, move=-1.5)]}
    cal = quant_eval.pooled_calibration(recs, ["naive"])
    assert cal["naive"]["inside_1sigma_pct"] == 50.0 and cal["naive"]["inside_2sigma_pct"] == 100.0
