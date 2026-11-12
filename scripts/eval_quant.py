"""Offline evaluation of the volatility models (design sections D3 and 5.2).

    python scripts/eval_quant.py              # use cached prices and records where they exist
    python scripts/eval_quant.py --refresh    # download prices again and recompute everything

Needs internet only for the first run (Yahoo Finance via yfinance). Prices are cached in eval/cache/prices so the
numbers can be reproduced without the network. Writes eval/results/quant-<date>.json and a short .md summary.

What it measures: does each model forecast the size of next month's moves better than a naive guess, is the stated
range honest, and which model should be the default. It says nothing about whether any stock goes up or down.

Honest limits (also written into the results file): US-listed stocks that still trade, so survivors are
over-represented; one data source with prices adjusted for later splits and dividends; test dates are about
a month apart, so each stock contributes about 35 test dates per three years."""
from __future__ import annotations

import datetime as dt
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.tools import market_data, quant, quant_eval  # noqa: E402

YEARS = 10
CACHE = ROOT / "eval" / "cache"
RESULTS = ROOT / "eval" / "results"
GROUP_CAP = 20                  # at most this many stocks per group, so no group dominates

LARGE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "BAC", "XOM", "CVX", "JNJ", "PFE", "WMT", "KO",
         "PG", "DIS", "NFLX", "INTC", "AMD", "BA", "CAT", "T", "NKE", "TSLA"]
MID = ["ALGN", "CROX", "ETSY", "FFIV", "GNRC", "HAS", "JBHT", "LKQ", "MTCH", "NVR", "POOL", "RL", "SNA", "TPR",
       "UHS", "URI", "WHR", "WYNN", "ZBRA", "DKS", "TXRH", "MTN", "BWA", "CHRW"]
# Candidates for the "fell hard" group. A stock only joins it if its price fell at least 50% from a prior peak at
# some point in the history: the rule below picks, not me.
FALLEN_POOL = ["AAL", "UAL", "DAL", "CCL", "NCLH", "RCL", "APA", "OXY", "HAL", "SLB", "DVN", "M", "KSS", "GPS", "VFC",
               "WBA", "PARA", "WBD", "LUMN", "PLUG", "SNAP", "PYPL", "ZM", "PTON", "MRNA", "COIN", "CHWY", "BYND",
               "EXPE", "MGM", "WYNN", "LVS", "SAVE", "HRB", "NWL", "F", "GE", "BBWI", "UAA"]
DRAWDOWN_RULE = 0.50


# ---- data ---------------------------------------------------------------------------------------------------------

def load_prices(ticker: str, refresh: bool) -> dict | None:
    """Daily closes from the cache, or from Yahoo (then cached). Today's possibly unfinished row is dropped."""
    path = CACHE / "prices" / f"{ticker}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    history = market_data.get_price_history(ticker, YEARS)
    if "error" in history:
        print(f"  {ticker}: {history['error']}", flush=True)
        return None
    today = dt.date.today().isoformat()
    if history["dates"][-1] >= today:
        history = {"dates": history["dates"][:-1], "closes": history["closes"][:-1]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history))
    return history


def max_drawdown_fraction(closes) -> float:
    prices = np.asarray(closes, dtype=float)
    return float(-np.min(prices / np.maximum.accumulate(prices) - 1))


def build_universe(refresh: bool) -> tuple[dict, dict]:
    """(groups, prices): which tickers are in which group, and their price histories."""
    prices: dict[str, dict] = {}
    groups: dict[str, list[str]] = {}
    for name, tickers in (("large", LARGE), ("mid", MID)):
        found = []
        for t in tickers:
            hist = load_prices(t, refresh)
            if hist and len(hist["closes"]) > quant.MIN_RETURNS:
                prices[t] = hist
                found.append(t)
        groups[name] = found[:GROUP_CAP]
    fallen = []
    for t in sorted(set(FALLEN_POOL)):
        if t in prices:                         # already in another group
            continue
        hist = load_prices(t, refresh)
        if hist and len(hist["closes"]) > quant.MIN_RETURNS and max_drawdown_fraction(hist["closes"]) >= DRAWDOWN_RULE:
            prices[t] = hist
            fallen.append(t)
    groups["fell_50pct"] = fallen[:GROUP_CAP]
    keep = {t for g in groups.values() for t in g}
    return groups, {t: prices[t] for t in keep}


# ---- computation --------------------------------------------------------------------------------------------------

def compute_records(args: tuple[str, dict, bool]) -> tuple[str, dict]:
    """Walk-forward records for one stock (runs in a worker process). Cached on disk."""
    ticker, hist, refresh = args
    path = CACHE / "records" / f"{ticker}.json"
    if path.exists() and not refresh:
        cached = json.loads(path.read_text())
        if cached.get("last_date") == hist["dates"][-1]:
            return ticker, cached
    returns = quant.log_returns(hist["closes"])
    records, skipped = quant.walk_forward_records(returns, hist["dates"], forecasters=quant.OFFLINE_FORECASTERS)
    out = {"last_date": hist["dates"][-1], "skipped": skipped, "records": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return ticker, out


def analyse(groups: dict, all_records: dict) -> dict:
    names = list(quant.OFFLINE_FORECASTERS)
    by_period: dict[str, dict[str, list]] = {"selection": {}, "heldout": {}}
    for ticker, recs in all_records.items():
        parts = quant_eval.split_by_period(recs["records"])
        for period, rows in parts.items():
            by_period[period][ticker] = rows

    selection_q = quant_eval.per_ticker_qlike(by_period["selection"], names)
    baseline = quant_eval.best_baseline(selection_q)
    selection = quant_eval.evaluate_period(by_period["selection"], names, baseline)
    decision = quant_eval.choose_default(selection, baseline)
    default = decision["default_model"]                       # what the written rule picked
    shipped = quant.resolve_model(config.QUANT_DEFAULT_MODEL)   # what the app actually uses; goals are checked for this

    heldout = quant_eval.evaluate_period(by_period["heldout"], names, baseline)
    held_cal = quant_eval.pooled_calibration(by_period["heldout"], names)
    sel_cal = quant_eval.pooled_calibration(by_period["selection"], names)

    per_group = {}
    for g, tickers in groups.items():
        sub = {t: by_period["heldout"][t] for t in tickers if t in by_period["heldout"]}
        q = quant_eval.per_ticker_qlike(sub, names)
        per_group[g] = {
            "tickers": len(q),
            "median_ratio_vs_naive": quant_eval.median_ratio(q, shipped, "naive"),
            "median_ratio_vs_best_baseline": quant_eval.median_ratio(q, shipped, baseline),
            "calibration": quant_eval.pooled_calibration(sub, [shipped]).get(shipped),
        }

    held_q = quant_eval.per_ticker_qlike(by_period["heldout"], names)
    held_best = quant_eval.best_baseline(held_q)
    robustness = {
        "best_baseline_in_selection": baseline, "best_baseline_in_heldout": held_best,
        "baseline_ranking_changed": baseline != held_best,
        "shipped_vs_heldout_best_baseline": None if shipped == held_best else {
            "baseline": held_best,
            "median_ratio": quant_eval.median_ratio(held_q, shipped, held_best),
            "dm": quant_eval.diebold_mariano(quant_eval.monthly_loss_differences(
                {t: by_period["heldout"][t] for t in held_q}, shipped, held_best)),
        },
    }

    shipped_held = heldout["models"][shipped]
    cal = held_cal.get(shipped, {})
    goals = {
        "G8_range_is_honest": {
            "target": "inside_1sigma_pct between 60 and 76",
            "measured": cal.get("inside_1sigma_pct"),
            "met": cal.get("inside_1sigma_pct") is not None and 60 <= cal["inside_1sigma_pct"] <= 76,
        },
        "G9_beats_naive_on_unseen_data": {
            "target": "median ratio vs naive below 1 and Diebold-Mariano p below 0.05, held-out period",
            "median_ratio": shipped_held["median_ratio_vs_naive"],
            "dm_vs_naive": shipped_held.get("dm_vs_naive"),
            "met": bool(shipped_held["median_ratio_vs_naive"] is not None and shipped_held["median_ratio_vs_naive"] < 1
                        and (shipped_held.get("dm_vs_naive") or {}).get("p_value", 1) < quant_eval.ALPHA),
        },
    }
    return {
        "run_date": dt.date.today().isoformat(),
        "horizon_trading_days": quant.HORIZON, "history_years": YEARS,
        "periods": {"selection_origin_dates_up_to": quant_eval.SELECTION_END,
                    "heldout_origin_dates_from": quant_eval.HELDOUT_START},
        "groups": groups,
        "best_baseline_in_selection": baseline,
        "decision": decision,
        "shipped_default": shipped,
        "rule_default": default,
        "selection": selection, "heldout": heldout,
        "calibration": {"selection": sel_cal, "heldout": held_cal},
        "robustness": robustness,
        "heldout_by_group": per_group,
        "goals": goals,
        "limits": [
            "Survivorship: only stocks that still trade are available; delisted ones are missing.",
            "Prices are adjusted for later splits and dividends (yfinance).",
            "Stocks move together; significance tests use one number per calendar month, not per stock-month.",
            "Test dates are about a month apart and windows do not overlap.",
            "Model variants beyond the baselines are evaluated here; the app uses whichever QUANT_DEFAULT_MODEL names.",
        ],
    }


def fmt_p(p) -> str:
    return "" if p is None else "<0.0001" if p < 0.0001 else f"{p:.4f}"


def markdown(r: dict) -> str:
    h, d = r["heldout"], r["decision"]["default_model"]
    lines = [
        f"# Volatility evaluation, {r['run_date']}", "",
        f"- Tickers: {', '.join(f'{g} {len(t)}' for g, t in r['groups'].items())}.",
        f"- Selection period: test dates up to {r['periods']['selection_origin_dates_up_to']}. "
        f"Held-out: from {r['periods']['heldout_origin_dates_from']}.",
        f"- Best simple baseline in the selection period: **{r['best_baseline_in_selection']}**.",
        f"- **Model the written rule picked: {d}** ({r['decision']['reason']}).",
        f"- **Model the app ships (`QUANT_DEFAULT_MODEL`): {r['shipped_default']}.** The goals and the group table "
        f"below are for this model.", "",
        "## Held-out results (median per-stock error ratio; lower than 1 is better than the reference)", "",
        "| Model | vs naive | vs best baseline | DM p vs naive | inside 1 sigma | inside 2 sigma |",
        "|---|---|---|---|---|---|",
    ]
    for m, e in h["models"].items():
        cal = r["calibration"]["heldout"].get(m, {})
        dm = fmt_p((e.get("dm_vs_naive") or {}).get("p_value"))
        lines.append(f"| {m} | {e['median_ratio_vs_naive']} | {e['median_ratio_vs_best_baseline']} | {dm} | "
                     f"{cal.get('inside_1sigma_pct')}% | {cal.get('inside_2sigma_pct')}% |")
    lines += ["", "Calibration targets for an honest range: about 68% inside 1 sigma and 95% inside 2 sigma.", "",
              "## Goals", ""]
    for g, v in r["goals"].items():
        lines.append(f"- **{g}**: {'MET' if v['met'] else 'NOT MET'} ({v['target']}).")
    lines += ["", "## Held-out by group (shipped default)", "",
              "| Group | Stocks | vs naive | vs best baseline | inside 1 sigma |", "|---|---|---|---|---|"]
    for g, v in r["heldout_by_group"].items():
        cal = v["calibration"] or {}
        lines.append(f"| {g} | {v['tickers']} | {v['median_ratio_vs_naive']} | "
                     f"{v['median_ratio_vs_best_baseline']} | {cal.get('inside_1sigma_pct')}% |")
    rb = r["robustness"]
    lines += ["", "## How solid is the choice?", "",
              f"- Rule check in the selection period: {json.dumps(r['decision']['checked'])}",
              f"- Best baseline in selection: **{rb['best_baseline_in_selection']}**; in held-out: "
              f"**{rb['best_baseline_in_heldout']}**" + (" (the ranking changed between periods)."
                                                          if rb["baseline_ranking_changed"] else ".")]
    hb = rb["shipped_vs_heldout_best_baseline"]
    if hb:
        lines.append(f"- Held-out, shipped default vs the held-out best baseline '{hb['baseline']}': median ratio "
                     f"{hb['median_ratio']}, Diebold-Mariano p = {fmt_p((hb['dm'] or {}).get('p_value'))}.")
    lines += ["", "## Limits", ""] + [f"- {x}" for x in r["limits"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    refresh = "--refresh" in sys.argv
    print("Loading prices...", flush=True)
    groups, prices = build_universe(refresh)
    print({g: len(t) for g, t in groups.items()}, flush=True)
    print(f"Computing walk-forward records for {len(prices)} stocks...", flush=True)
    jobs = [(t, prices[t], refresh) for t in sorted(prices)]
    all_records = {}
    try:
        pool = ProcessPoolExecutor(max_workers=4)
    except PermissionError:                       # some sandboxes forbid worker processes; one at a time works
        print("  (worker processes not allowed here; running one stock at a time)", flush=True)
        pool = None
    results = pool.map(compute_records, jobs) if pool else map(compute_records, jobs)
    for ticker, out in results:
        all_records[ticker] = out
        print(f"  {ticker}: {len(out['records'])} test dates, {out['skipped']} skipped", flush=True)
    if pool:
        pool.shutdown()
    result = analyse(groups, all_records)
    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = RESULTS / f"quant-{result['run_date']}"
    stem.with_suffix(".json").write_text(json.dumps(result, indent=1))
    stem.with_suffix(".md").write_text(markdown(result))
    print("\n" + markdown(result))
    print(f"Wrote {stem}.json and .md")


if __name__ == "__main__":
    main()
