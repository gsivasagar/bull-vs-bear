"""Numbers for the live-model evaluation (consistency, position bias, faithfulness, latency, tokens).

Each run is a dict: {"ticker", "order" ("bull_first"/"bear_first"), "rep", "recommendation", "seconds", "usage",
"faithfulness": {"bull": {...}, "bear": {...}, "judge": {...}}, "error"}.
Failed runs (error set) are counted, not hidden."""
from collections import Counter
from statistics import median
from typing import Any, Dict, List


def _ok(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in runs if not r.get("error") and r.get("recommendation") in ("BUY", "SELL", "HOLD")]


def flip_rate(runs: List[Dict[str, Any]], order: str = "bull_first") -> Dict[str, Any]:
    """Per ticker, the share of repeat runs whose verdict differs from that ticker's most common verdict.
    Also the overall mean across tickers. Needs at least 2 good runs per ticker to count."""
    per_ticker: Dict[str, float] = {}
    for ticker in sorted({r["ticker"] for r in runs}):
        votes = [r["recommendation"] for r in _ok(runs) if r["ticker"] == ticker and r["order"] == order]
        if len(votes) >= 2:
            modal = Counter(votes).most_common(1)[0][1]
            per_ticker[ticker] = round(1 - modal / len(votes), 4)
    mean = round(sum(per_ticker.values()) / len(per_ticker), 4) if per_ticker else None
    return {"per_ticker": per_ticker, "mean": mean, "tickers": len(per_ticker)}


def order_change_rate(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pairs (same ticker, same repetition) run with Bull first and Bear first: how often does the verdict change?
    Also which side wins more often when it is shown first."""
    good = {(r["ticker"], r["rep"], r["order"]): r["recommendation"] for r in _ok(runs)}
    pairs = [(good[(t, rep, "bull_first")], good[(t, rep, "bear_first")])
             for (t, rep, o) in good if o == "bull_first" and (t, rep, "bear_first") in good]
    if not pairs:
        return {"pairs": 0, "changed_share": None}
    changed = sum(a != b for a, b in pairs)
    return {"pairs": len(pairs), "changed": changed, "changed_share": round(changed / len(pairs), 4)}


def faithfulness_share(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Share of cited numbers that exist in the data, pooled over runs, for each writer."""
    out: Dict[str, Any] = {}
    for who in ("bull", "bear", "judge"):
        checked = supported = 0
        for r in _ok(runs):
            f = (r.get("faithfulness") or {}).get(who) or {}
            checked += f.get("checked", 0)
            supported += f.get("supported", 0)
        out[who] = {"checked": checked, "supported": supported,
                    "share": round(supported / checked, 4) if checked else None}
    total_checked = sum(v["checked"] for v in out.values())
    total_supported = sum(v["supported"] for v in out.values())
    out["all"] = {"checked": total_checked, "supported": total_supported,
                  "share": round(total_supported / total_checked, 4) if total_checked else None}
    return out


def latency_and_tokens(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = _ok(runs)
    secs = sorted(r["seconds"] for r in ok if isinstance(r.get("seconds"), (int, float)))
    if not secs:
        return {"runs": 0}
    p95 = secs[min(len(secs) - 1, int(round(0.95 * (len(secs) - 1))))]
    tin = [r["usage"]["input_tokens"] for r in ok if r.get("usage")]
    tout = [r["usage"]["output_tokens"] for r in ok if r.get("usage")]
    return {"runs": len(secs), "median_seconds": round(median(secs), 1), "p95_seconds": round(p95, 1),
            "median_input_tokens": int(median(tin)) if tin else None,
            "median_output_tokens": int(median(tout)) if tout else None}


def summarize(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = sum(1 for r in runs if r.get("error"))
    return {"runs": len(runs), "failed": failed, "unclear_verdicts": len(runs) - failed - len(_ok(runs)),
            "verdict_counts": dict(Counter(r["recommendation"] for r in _ok(runs))),
            "consistency": flip_rate(runs), "position_bias": order_change_rate(runs),
            "faithfulness": faithfulness_share(runs), "cost": latency_and_tokens(runs)}
