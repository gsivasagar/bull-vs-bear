"""Statistics for the offline volatility evaluation (design D3 and section 5.2).

Kept apart from quant.py because the request path never needs it. Everything here works on the per-date records that
`quant.walk_forward_records` produces, so it is plain arithmetic that tests can check by hand."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

import numpy as np
from scipy import stats

from src.tools import quant

BASELINES = quant.BASELINES
CANDIDATES = ("garch", "garch_t", "gjr")
MIN_DATES = 12                 # a stock needs this many scored dates in a period to count in that period
RATIO_THRESHOLD = 0.95         # a candidate must have a median error ratio at or below this versus the best baseline
ALPHA = 0.05

# Test dates are about one month apart and each forecasts the next 21 trading days. Selection dates stop a month early
# so no selection window reaches into the held-out period.
SELECTION_END = "2023-11-30"
HELDOUT_START = "2024-01-02"


def split_by_period(records: List[dict]) -> Dict[str, List[dict]]:
    return {
        "selection": [r for r in records if r["date"] and r["date"] <= SELECTION_END],
        "heldout": [r for r in records if r["date"] and r["date"] >= HELDOUT_START],
    }


def record_loss(record: dict, model: str) -> float:
    return quant.qlike(record["forecasts"][model], record["realized_var"])


def newey_west_variance_of_mean(d: np.ndarray, lags: int) -> float:
    """Variance of the mean of a serially correlated series (Bartlett weights)."""
    n = len(d)
    centred = d - d.mean()
    total = float(np.dot(centred, centred)) / n
    for lag in range(1, lags + 1):
        weight = 1 - lag / (lags + 1)
        total += 2 * weight * float(np.dot(centred[lag:], centred[:-lag])) / n
    return total / n


def diebold_mariano(d: np.ndarray) -> Dict[str, Any] | None:
    """One-sided test that the mean of `d` is above zero, where d = baseline loss - model loss (positive: model better).

    Uses Newey-West standard errors and a t distribution with n-1 degrees of freedom. Returns None when there are too
    few months to say anything."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    if n < 8:
        return None
    lags = int(np.floor(n ** (1 / 3)))
    variance = newey_west_variance_of_mean(d, lags)
    if variance <= 0:
        return {"months": n, "mean_diff": float(d.mean()), "t_stat": None, "p_value": 1.0, "lags": lags}
    t_stat = float(d.mean() / np.sqrt(variance))
    return {"months": n, "mean_diff": round(float(d.mean()), 5), "t_stat": round(t_stat, 3),
            "p_value": round(float(stats.t.sf(t_stat, n - 1)), 4), "lags": lags}


def monthly_loss_differences(records_by_ticker: Dict[str, List[dict]], model: str, baseline: str) -> np.ndarray:
    """One number per calendar month: the average over stocks of (baseline loss - model loss).

    Stocks move together, so the months, not the stock-months, are the independent units."""
    by_month: Dict[str, List[float]] = defaultdict(list)
    for recs in records_by_ticker.values():
        for r in recs:
            by_month[r["date"][:7]].append(record_loss(r, baseline) - record_loss(r, model))
    return np.array([float(np.mean(by_month[k])) for k in sorted(by_month)])


def per_ticker_qlike(records_by_ticker: Dict[str, List[dict]], names) -> Dict[str, Dict[str, float]]:
    out = {}
    for ticker, recs in records_by_ticker.items():
        if len(recs) >= MIN_DATES:
            out[ticker] = {m: float(np.mean([record_loss(r, m) for r in recs])) for m in names}
    return out


def median_ratio(qlikes: Dict[str, Dict[str, float]], model: str, baseline: str) -> float | None:
    ratios = [q[model] / q[baseline] for q in qlikes.values() if q[baseline] > 0]
    return round(float(np.median(ratios)), 4) if ratios else None


def best_baseline(qlikes: Dict[str, Dict[str, float]]) -> str:
    """The baseline with the lowest median error ratio versus the naive guess (naive itself scores 1)."""
    return min(BASELINES, key=lambda b: median_ratio(qlikes, b, "naive") or float("inf"))


def evaluate_period(records_by_ticker: Dict[str, List[dict]], names, baseline: str) -> Dict[str, Any]:
    """Median error ratios and Diebold-Mariano tests for every model in one period."""
    qlikes = per_ticker_qlike(records_by_ticker, names)
    usable = {t: records_by_ticker[t] for t in qlikes}
    out: Dict[str, Any] = {"tickers": len(qlikes), "models": {}}
    for m in names:
        entry = {"median_ratio_vs_naive": median_ratio(qlikes, m, "naive"),
                 "median_ratio_vs_best_baseline": median_ratio(qlikes, m, baseline)}
        if m != "naive":
            entry["dm_vs_naive"] = diebold_mariano(monthly_loss_differences(usable, m, "naive"))
        if m != baseline:
            entry["dm_vs_best_baseline"] = diebold_mariano(monthly_loss_differences(usable, m, baseline))
        out["models"][m] = entry
    return out


def choose_default(selection: Dict[str, Any], baseline: str) -> Dict[str, Any]:
    """Apply the design D3 rule to the selection period (and only to it).

    A candidate replaces the best baseline if its median error ratio is at most 0.95 AND the Diebold-Mariano test
    favours it at the 5% level. Among those that pass, the lowest ratio wins."""
    passing, notes = [], {}
    for m in CANDIDATES:
        entry = selection["models"].get(m)
        if not entry:
            continue
        ratio = entry["median_ratio_vs_best_baseline"]
        dm = entry.get("dm_vs_best_baseline")
        p = dm["p_value"] if dm else None
        ok = ratio is not None and ratio <= RATIO_THRESHOLD and p is not None and p < ALPHA
        notes[m] = {"median_ratio": ratio, "p_value": p, "passes": ok}
        if ok:
            passing.append((ratio, m))
    if passing:
        winner = min(passing)[1]
        return {"default_model": winner, "reason": f"{winner} passed the rule; best baseline was '{baseline}'",
                "checked": notes}
    return {"default_model": baseline, "reason": f"no candidate beat the best baseline '{baseline}' by the rule",
            "checked": notes}


def pooled_calibration(records_by_ticker: Dict[str, List[dict]], names) -> Dict[str, Any]:
    """Share of real moves inside the stated +-1 and +-2 sigma ranges, pooled over stocks and dates."""
    pooled = [r for recs in records_by_ticker.values() for r in recs]
    return quant.score_records(pooled, names) if pooled else {}
