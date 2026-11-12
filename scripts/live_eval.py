"""Run real debates against a live model and measure them (needs GEMINI_API_KEY in the environment).

    GEMINI_API_KEY=... python -m scripts.live_eval --plan smoke            # print the plan and cost; nothing runs
    GEMINI_API_KEY=... python -m scripts.live_eval --plan smoke --yes      # C2: 10 tickers, 1 run each
    GEMINI_API_KEY=... python -m scripts.live_eval --plan full --yes       # D3/D4: 10 tickers x 5 repeats x 2 orders

Every debate is 3 model calls (Bull, Bear, Judge). The key is read from the environment and never written to a file.
Results go to eval/results/live-<date>.json and .md, including failed runs."""
import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from src import config
from src.agents import nodes
from src.api import _initial_state, build_result, summarize_usage
from src.errors import DebateError
from src.graph import create_graph
from src.tools import faithfulness, live_stats

TICKERS = ["NVDA", "AAPL", "MSFT", "TSLA", "KO", "JPM", "F", "PLTR", "INTC", "XOM"]
BOTH = ["bull_first", "bear_first"]
PLANS = {"smoke": {"tickers": TICKERS, "repeats": 1, "orders": ["bull_first"]},
         # 3 tickers x 3 repeats x both orders = 18 debates (54 calls): small enough for a free key, enough for a first
         # look at consistency (3 runs per ticker and order) and position bias (9 pairs).
         "medium": {"tickers": ["NVDA", "KO", "INTC"], "repeats": 3, "orders": BOTH},
         "full": {"tickers": TICKERS, "repeats": 5, "orders": BOTH}}
EXAMPLES = Path(__file__).resolve().parent.parent / "demo" / "examples"
WRITERS = (("bull", "bull_argument"), ("bear", "bear_argument"), ("judge", "verdict"))
OUT = Path(__file__).resolve().parent.parent / "eval" / "results"


def evidence(state: dict) -> dict:
    """The same data block the agents saw (so cited numbers are checked against exactly that)."""
    return {"price_data": state.get("price_data"), "financials": state.get("financials"),
            "quant": nodes.agent_view(state.get("quant") or {})}


def one_run(graph, key: str, ticker: str, order: str, rep: int, save_example: bool = False) -> dict:
    started = time.monotonic()
    row = {"ticker": ticker, "order": order, "rep": rep}
    try:
        state = _initial_state(ticker, key)
        state["judge_order"] = order
        out = graph.invoke(state)
    except DebateError as exc:
        return {**row, "error": f"{exc.status_code} {exc.public_message}",
                "seconds": round(time.monotonic() - started, 1)}
    data, news = evidence(out), out.get("news_data") or []
    if save_example:                                   # a saved real debate the demo can show without a model call
        EXAMPLES.mkdir(parents=True, exist_ok=True)
        saved = {**build_result({**out, "ticker": ticker}), "saved_on": date.today().isoformat(),
                 "model": config.GEMINI_MODEL}
        (EXAMPLES / f"{ticker}.json").write_text(json.dumps(saved, indent=1))
    return {**row, "recommendation": out.get("recommendation"),
            "confidence": (out.get("judge") or {}).get("confidence"),
            "structured": bool(out.get("judge")), "seconds": round(time.monotonic() - started, 1),
            "usage": summarize_usage(out.get("usage") or []),
            "evidence": data,
            # kept so that unsupported numbers can be audited by hand
            "texts": {who: out.get(field, "") for who, field in WRITERS},
            "faithfulness": {who: faithfulness.check(out.get(field, ""), data, news)
                             for who, field in WRITERS}}


def write(runs: list, plan: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    summary = live_stats.summarize(runs)
    body = {"date": stamp, "plan": plan, "model": config.GEMINI_MODEL, "summary": summary, "runs": runs}
    (OUT / f"live-{stamp}-{plan}.json").write_text(json.dumps(body, indent=1))
    s = summary
    md = [f"# Live-model evaluation, {stamp}", "", f"Model: `{config.GEMINI_MODEL}`. Plan: `{plan}`. Runs: {s['runs']} "
          f"(failed {s['failed']}, unclear verdict {s['unclear_verdicts']}). Verdicts: {s['verdict_counts']}.", "",
          f"- Consistency: mean flip rate {s['consistency']['mean']} over {s['consistency']['tickers']} tickers",
          f"- Position bias: verdict changed in {s['position_bias']['changed_share']} "
          f"of {s['position_bias']['pairs']} pairs",
          f"- Faithfulness (cited numbers found in the data): {s['faithfulness']['all']['share']} "
          f"of {s['faithfulness']['all']['checked']}",
          f"- Cost: {s['cost']}", "", "Per-run detail is in the JSON file next to this one."]
    (OUT / f"live-{stamp}-{plan}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return OUT / f"live-{stamp}-{plan}.json"


def keys_from_env() -> list:
    """GEMINI_API_KEY and, optionally, GEMINI_API_KEY_2 (used in turn to spread a free-tier quota)."""
    return [k for k in (os.getenv("GEMINI_API_KEY", "").strip(), os.getenv("GEMINI_API_KEY_2", "").strip()) if k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", choices=PLANS, default="smoke")
    ap.add_argument("--yes", action="store_true", help="actually call the model (spends quota or money)")
    ap.add_argument("--pause", type=float, default=0, help="seconds to wait between debates (free-tier limits)")
    ap.add_argument("--examples", action="store_true", help="save one debate per ticker as a demo example")
    args = ap.parse_args()
    plan = PLANS[args.plan]
    runs_planned = len(plan["tickers"]) * plan["repeats"] * len(plan["orders"])
    print(f"Plan '{args.plan}': {runs_planned} debates x 3 model calls = {runs_planned * 3} calls "
          f"on {config.GEMINI_MODEL}")
    if not args.yes:
        print("Dry run. Add --yes to execute.")
        return 0
    keys = keys_from_env()
    if not keys:
        print("Set GEMINI_API_KEY in the environment (never in a file).")
        return 1
    graph, runs, n = create_graph(), [], 0
    saved = OUT / f"live-{date.today().isoformat()}-{args.plan}.json"
    if saved.exists():                                      # resume: keep what already worked, redo only the failures
        runs = [r for r in json.loads(saved.read_text())["runs"] if not r.get("error")]
    done = {(r["ticker"], r["order"], r["rep"]) for r in runs}
    for rep in range(plan["repeats"]):
        for order in plan["orders"]:
            for ticker in plan["tickers"]:
                if (ticker, order, rep) in done:
                    continue
                example = args.examples and rep == 0 and order == "bull_first"
                for attempt in (0, 1):                      # on a rate limit, wait a minute and try the other key
                    row = one_run(graph, keys[n % len(keys)], ticker, order, rep, example)
                    n += 1
                    if not (row.get("error") or "").startswith("429") or attempt:
                        break
                    print(f"{ticker}: rate limited, waiting 90 s", flush=True)
                    time.sleep(90)
                runs.append(row)
                print(f"{ticker} rep={rep} {order}: {row.get('recommendation') or row.get('error')}", flush=True)
                write(runs, args.plan)                      # saved after every run so a quota stop loses nothing
                time.sleep(args.pause)
    return 0


if __name__ == "__main__":
    sys.exit(main())
