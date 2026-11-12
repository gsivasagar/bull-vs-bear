"""Quantitative signals: how much a stock is likely to swing over the next month, and how well that method has done.

Why volatility and not price direction: volatility clusters (calm periods follow calm periods, wild follow wild), so it
can be forecast better than a naive guess. Direction cannot, in any way this module could honestly claim. The block
therefore carries no direction forecast, and the agents are told so.

Which method runs on a request is decided in advance, offline, not per stock: `QUANT_DEFAULT_MODEL` (default
`long_run`, the one-year average). The evaluation behind that choice is `scripts/eval_quant.py` and its results in
`eval/results/`. Per stock, this module only *reports* how the chosen method scored on that stock's own past months.

Two views of the result: the full block (browser) and `agent_view` (the agents), which leaves out model scores and
the past-months-up base rate so neither can be mistaken for a direction signal.
Design: docs/DESIGN_QUANT_AND_AGENT_TOOLS.md.
"""
from __future__ import annotations

import logging
import time
import warnings
from typing import Any, Callable, Dict

import numpy as np

from src import config
from src.cache import ttl_cache
from src.tools import market_data

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1           # bump when a field in the block is renamed or removed (the web page depends on it)
TRADING_DAYS = 252
HORIZON = 21                 # about one month of trading days
MIN_TRAIN = 504              # two years of returns before the first test date
STEP = HORIZON               # test dates are one horizon apart, so test windows do not overlap
MIN_RETURNS = MIN_TRAIN + 2 * HORIZON
MIN_TRACK_DATES = 12         # fewer scored months than this and we say the record is too short to judge
GARCH_WINDOW = 1000          # the GARCH fit never uses more than the latest 1,000 returns
EWMA_LAMBDA = 0.94           # the RiskMetrics default
BASELINES = ("naive", "long_run", "ewma")
FALLBACK_ORDER = ("long_run", "ewma", "naive")

METHOD_LABELS = {
    "naive": "last-month", "long_run": "one-year-average", "ewma": "recent-weighted (EWMA)",
    "garch": "GARCH", "garch_t": "GARCH (fat tails)", "gjr": "GJR-GARCH",
}

CAVEATS = [
    "This forecasts how much the price may move, not which way. No direction forecast is made.",
    "The track record comes from this stock's own recent months; past accuracy does not guarantee future accuracy.",
]


# ---- helpers ---------------------------------------------------------------------------------------------------

def log_returns(closes) -> np.ndarray:
    prices = np.asarray(closes, dtype=float)
    if prices.ndim != 1 or len(prices) < 2 or not np.all(np.isfinite(prices)) or np.any(prices <= 0):
        raise ValueError("prices must be a 1-D series of positive numbers")
    return np.diff(np.log(prices))


def annualize(daily_variance: float) -> float:
    """Daily variance of log returns to annualized volatility, in percent."""
    return float(np.sqrt(max(daily_variance, 0.0) * TRADING_DAYS) * 100)


def mean_square(returns: np.ndarray) -> float:
    return float(np.mean(np.square(returns)))


# ---- forecasts: each returns the expected average DAILY variance over the next `horizon` days -------------------
# All take only the returns known so far. None of them may look past the end of the array.

def forecast_naive(returns: np.ndarray, horizon: int) -> float:
    """Baseline 1: the next month will be as wild as the last month."""
    return mean_square(returns[-HORIZON:])


def forecast_long_run(returns: np.ndarray, horizon: int) -> float:
    """Baseline 2 (the default): the next month will be like the last year."""
    return mean_square(returns[-TRADING_DAYS:])


def forecast_ewma(returns: np.ndarray, horizon: int) -> float:
    """Baseline 3: recent days count more (RiskMetrics, lambda 0.94); a flat forecast from the latest estimate."""
    variance = mean_square(returns[:HORIZON])                       # seed from the first month of the window
    for r in returns[HORIZON:]:
        variance = EWMA_LAMBDA * variance + (1 - EWMA_LAMBDA) * r * r
    return float(variance)


def _garch_family(returns: np.ndarray, horizon: int, *, dist: str = "normal", asym: int = 0) -> float:
    """GARCH(1,1)-type model: volatility that reacts to shocks and drifts back toward its long-run level.

    `dist` is the error distribution ("normal" or "t"); `asym=1` adds the GJR term (falls raise volatility more than
    rises). Returns are scaled to percent for the optimiser, then scaled back. Raises if the fit does not converge.
    Needs the `arch` package (requirements-dev.txt); the request path does not use it by default."""
    from arch import arch_model  # imported late: only these models need it

    window = returns[-GARCH_WINDOW:] * 100
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = arch_model(window, mean="Zero", vol="GARCH", p=1, o=asym, q=1, dist=dist, rescale=False).fit(
            disp="off", show_warning=False)
    if result.convergence_flag != 0:
        raise RuntimeError("GARCH fit did not converge")
    path = np.asarray(result.forecast(horizon=horizon, reindex=False).variance)[-1]
    value = float(np.mean(path)) / 10_000
    if not np.isfinite(value) or value <= 0:
        raise RuntimeError("GARCH produced an unusable forecast")
    return value


def forecast_garch(returns: np.ndarray, horizon: int) -> float:
    return _garch_family(returns, horizon)


def forecast_garch_t(returns: np.ndarray, horizon: int) -> float:
    """GARCH(1,1) with fat-tailed Student-t errors. Offline evaluation only."""
    return _garch_family(returns, horizon, dist="t")


def forecast_gjr(returns: np.ndarray, horizon: int) -> float:
    """GJR-GARCH(1,1,1): bad days raise volatility more than good days."""
    return _garch_family(returns, horizon, asym=1)


Forecaster = Callable[[np.ndarray, int], float]

# Cheap models that need no extra packages. These are what a request scores a stock's track record against.
FORECASTERS: Dict[str, Forecaster] = {
    "naive": forecast_naive, "long_run": forecast_long_run, "ewma": forecast_ewma,
}
# Everything the offline evaluation compares. Any of these can be configured as the default, but only the baselines
# are fast; the GARCH family adds seconds per cold request.
OFFLINE_FORECASTERS: Dict[str, Forecaster] = {**FORECASTERS, "garch": forecast_garch, "garch_t": forecast_garch_t,
                                              "gjr": forecast_gjr}


def forecasts_at(returns: np.ndarray, t: int, horizon: int = HORIZON,
                 forecasters: Dict[str, Forecaster] | None = None) -> Dict[str, float]:
    """Every model's forecast made at index t, using returns[:t] only."""
    known = returns[:t]
    return {name: fn(known, horizon) for name, fn in (forecasters or FORECASTERS).items()}


# ---- scoring ----------------------------------------------------------------------------------------------------

def qlike(forecast_var: float, realized_var: float) -> float:
    """QLIKE loss: 0 for a perfect forecast, and it punishes under-forecasting more than over-forecasting.

    This is the loss recommended for comparing volatility forecasts because it is not thrown off by one wild month."""
    ratio = realized_var / forecast_var
    return float(ratio - np.log(ratio) - 1)


def walk_forward_records(returns: np.ndarray, dates=None, horizon: int = HORIZON,
                         forecasters: Dict[str, Forecaster] | None = None):
    """Forecast at past dates, each time seeing only the data before that date.

    Returns (records, skipped). A record holds the test date, the realized variance and move over the next `horizon`
    days, and every model's forecast. A date where any model fails is dropped for ALL models, so they stay comparable.
    `dates[i]` is the date of price i, so returns[:t] ends at price t and the forecast is made on dates[t]."""
    chosen = forecasters or FORECASTERS
    records, skipped = [], 0
    for t in range(MIN_TRAIN, len(returns) - horizon + 1, STEP):
        window = returns[t:t + horizon]
        realized = mean_square(window)
        if realized <= 0:
            skipped += 1
            continue
        try:
            forecasts = forecasts_at(returns, t, horizon, chosen)
        except Exception as exc:
            log.info("Skipping test date %d: %s", t, exc)
            skipped += 1
            continue
        if not all(np.isfinite(v) and v > 0 for v in forecasts.values()):
            skipped += 1
            continue
        records.append({"t": t, "date": dates[t] if dates is not None else None, "realized_var": realized,
                        "move": float(np.sum(window)), "forecasts": forecasts})
    return records, skipped


def score_records(records, names, horizon: int = HORIZON) -> Dict[str, Any]:
    """Average error and calibration per model. Calibration is the share of real moves inside the stated +-1 and
    +-2 sigma ranges (about 68% and 95% if the forecast is honest)."""
    if not records:
        return {}
    scores = {}
    for m in names:
        forecast = np.array([r["forecasts"][m] for r in records])
        realized = np.array([r["realized_var"] for r in records])
        move = np.abs(np.array([r["move"] for r in records]))
        sigma = np.sqrt(forecast * horizon)
        vol_error = np.array([annualize(f) - annualize(x) for f, x in zip(forecast, realized, strict=True)])
        scores[m] = {
            "qlike": round(float(np.mean([qlike(f, x) for f, x in zip(forecast, realized, strict=True)])), 4),
            "rmse_vol_pts": round(float(np.sqrt(np.mean(np.square(vol_error)))), 2),
            "inside_1sigma_pct": round(float(np.mean(move <= sigma) * 100), 1),
            "inside_2sigma_pct": round(float(np.mean(move <= 2 * sigma) * 100), 1),
        }
    return scores


# ---- the request path -------------------------------------------------------------------------------------------

def resolve_model(name: str | None) -> str:
    """The configured default if it names a known model, else the one-year average (with a warning)."""
    if name in OFFLINE_FORECASTERS:
        return name  # type: ignore[return-value]
    log.warning("Unknown QUANT_DEFAULT_MODEL %r; using long_run", name)
    return "long_run"


def forecast_today(returns: np.ndarray, model: str, horizon: int = HORIZON):
    """(model used, fallback used?, daily variance). Tries `model`, then the simple models in FALLBACK_ORDER."""
    order = [model] + [m for m in FALLBACK_ORDER if m != model]
    for i, name in enumerate(order):
        try:
            value = OFFLINE_FORECASTERS[name](returns, horizon)
        except Exception as exc:
            log.warning("%s forecast failed: %s", name, exc)
            continue
        if np.isfinite(value) and value > 0:
            return name, i > 0, float(value)
    raise RuntimeError("no volatility model produced a usable forecast")


def track_record(returns: np.ndarray, dates, model: str, horizon: int = HORIZON) -> Dict[str, Any]:
    """How `model` and the simple baselines scored on this stock's own past months (each seeing only earlier data)."""
    names = list(dict.fromkeys([*BASELINES, model]))
    records, skipped = walk_forward_records(returns, dates, horizon, {n: OFFLINE_FORECASTERS[n] for n in names})
    if len(records) < MIN_TRACK_DATES:
        return {"status": "unavailable", "test_dates": len(records), "skipped": skipped, "scores": {},
                "calibration": {}}
    scores = score_records(records, names, horizon)
    chosen = scores[model]
    return {"status": "ready", "test_dates": len(records), "skipped": skipped, "scores": scores,
            "calibration": {"inside_1sigma_pct": chosen["inside_1sigma_pct"],
                            "inside_2sigma_pct": chosen["inside_2sigma_pct"]}}


def summary_sentence(model: str, fallback_used: bool, track: Dict[str, Any]) -> str:
    """One honest sentence about the method's record on this stock. Written by code, never by the language model."""
    label = METHOD_LABELS.get(model, model)
    prefix = "The usual method failed today, so a simpler one was used. " if fallback_used else ""
    n = track.get("test_dates", 0)
    if track.get("status") != "ready":
        return f"{prefix}Forecast from the {label} method. Too little history ({n} months) to score it for this stock."
    if model == "naive":
        return f"{prefix}Forecast from the {label} method, which is the naive guess itself, so it has nothing to beat."
    scores = track["scores"]
    gain = (1 - scores[model]["qlike"] / scores["naive"]["qlike"]) * 100
    if gain > 0:
        inside = scores[model]["inside_1sigma_pct"]
        return (f"{prefix}Forecast from the {label} method. On this stock's past {n} months it had {gain:.0f}% lower "
                f"error than the naive guess (next month equals last month); real moves fell inside the stated "
                f"range in {inside:.0f}% of months (about 68% expected).")
    return (f"{prefix}Forecast from the {label} method. On this stock's past {n} months it did not beat the naive "
            f"guess (next month equals last month); treat it with caution.")


# ---- context numbers --------------------------------------------------------------------------------------------

def rolling_vol(returns: np.ndarray, window: int = HORIZON) -> np.ndarray:
    squared = np.square(returns)
    cumulative = np.concatenate([[0.0], np.cumsum(squared)])
    return np.sqrt((cumulative[window:] - cumulative[:-window]) / window * TRADING_DAYS) * 100


def vol_regime(returns: np.ndarray) -> Dict[str, Any]:
    """Where today's one-month volatility sits within the last year of one-month volatilities."""
    series = rolling_vol(returns)[-TRADING_DAYS:]
    current = float(series[-1])
    percentile = float(np.mean(series <= current) * 100)
    label = "high" if percentile >= 75 else "low" if percentile <= 25 else "normal"
    return {"current_pct": round(current, 1), "percentile_1y": round(percentile), "regime": label}


def max_drawdown(closes: np.ndarray) -> float:
    peaks = np.maximum.accumulate(closes)
    return float(np.min(closes / peaks - 1) * 100)


def price_context(closes: np.ndarray) -> Dict[str, Any]:
    def change(days: int) -> float | None:
        return round(float((closes[-1] / closes[-1 - days] - 1) * 100), 1) if len(closes) > days else None

    forward = closes[HORIZON:] / closes[:-HORIZON] - 1                # every 21-day window in the history
    return {
        "return_1m_pct": change(21), "return_3m_pct": change(63), "return_6m_pct": change(126),
        "max_drawdown_1y_pct": round(max_drawdown(closes[-TRADING_DAYS:]), 1),
        "past_months_up_pct": round(float(np.mean(forward > 0) * 100)) if len(forward) else None,
        "past_months_up_note": "past base rate, not a forecast",
    }


# ---- public entry points ----------------------------------------------------------------------------------------

def analyze(closes, dates=None, model: str | None = None, horizon: int = HORIZON) -> Dict[str, Any]:
    """The full block (schema version 1) from a series of daily closes, oldest first."""
    try:
        returns = log_returns(closes)
    except ValueError:
        return {"error": "Price history is not usable", "kind": "bad_data"}
    if len(returns) < MIN_RETURNS:
        return {"error": f"Need about {MIN_RETURNS // TRADING_DAYS + 1} years of daily prices; got {len(returns)} days",
                "kind": "insufficient_data"}

    requested = resolve_model(model if model is not None else config.QUANT_DEFAULT_MODEL)
    try:
        used, fallback, variance = forecast_today(returns, requested, horizon)
    except RuntimeError:
        return {"error": "No volatility model could produce a forecast", "kind": "failed"}

    track = track_record(returns, dates, used, horizon)           # score the model that was actually used
    forecast = annualize(variance)
    one_sigma = forecast * np.sqrt(horizon / TRADING_DAYS)
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": dates[-1] if dates else None,
        "horizon_trading_days": horizon,
        "volatility": {
            "model": used,
            "method": METHOD_LABELS.get(used, used),
            "fallback_used": fallback,
            "forecast_annualized_pct": round(forecast, 1),
            "one_sigma_move_over_horizon_pct": round(float(one_sigma), 1),
            **vol_regime(returns),
        },
        "track_record": {**track, "summary": summary_sentence(used, fallback, track)},
        "price": price_context(np.asarray(closes, dtype=float)),
        "caveats": CAVEATS,
    }


def agent_view(block: Dict[str, Any]) -> Dict[str, Any]:
    """What the language-model agents see: the forecast, the regime, recent moves and one honest sentence.

    Deliberately leaves out the per-model scores (easy to misquote) and the past-months-up base rate (easy to read as a
    probability of a rise)."""
    if not block:
        return {}
    v, t, p = block.get("volatility", {}), block.get("track_record", {}), block.get("price", {})
    return {
        "horizon_trading_days": block.get("horizon_trading_days"),
        "as_of": block.get("as_of"),
        "volatility": {k: v.get(k) for k in ("method", "forecast_annualized_pct", "one_sigma_move_over_horizon_pct",
                                              "regime", "percentile_1y")},
        "recent": {k: p.get(k) for k in ("return_1m_pct", "return_3m_pct", "return_6m_pct", "max_drawdown_1y_pct")},
        "summary": t.get("summary"),
        "note": (block.get("caveats") or [""])[0],
    }


@ttl_cache(lambda: config.QUANT_FORECAST_TTL_SECONDS, single_flight=True)
def get_quant_signals(ticker: str) -> Dict[str, Any]:
    """Quant block for a ticker. Returns {"error": ...} when switched off, or when the history is missing or short."""
    if not config.QUANT_ENABLED:
        return {"error": "Quant signals are switched off", "kind": "disabled"}
    start = time.perf_counter()
    history = market_data.get_price_history(ticker)
    if "error" in history:
        return history
    block = analyze(history["closes"], history["dates"])
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if "error" in block:
        log.info("quant ticker=%s ms=%d error=%s", ticker, elapsed_ms, block["kind"])
        return block
    log.info("quant ticker=%s ms=%d model=%s fallback=%s track_record=%s test_dates=%d", ticker, elapsed_ms,
             block["volatility"]["model"], block["volatility"]["fallback_used"], block["track_record"]["status"],
             block["track_record"]["test_dates"])
    return block
