# Design: quantitative signals and agent tool use for Bull vs Bear

Status: **APPROVED (as recommended) on 2026-11-09. Phase 1a and 1b are built; Phases 3 and 4 are not. Phase 2 is dropped (Q1 = B).**
Date: 2026-11-09

How to read this: section 1 is the plan, section 2 the architecture decisions, section 3 the high-level design (HLD),
section 4 the low-level design (LLD), section 5 the test and evaluation plan, section 6 the phases, section 7 the
questions only you can answer.

### Changes from v1 (after review)

| # | Review finding | Where fixed |
|---|---|---|
| 1 | "839 test months" overstated the evidence; survivorship bias not mentioned | 1.5, D3, 5.2 |
| 2 | Default-model rule chose and reported on the same data, and averaged across stocks | D3, 5.2 |
| 3 | Full backtest ran on every request (about 3 s) | D8, 3.2, 3.5, 4.4 |
| 4 | A base rate ("share of months up") could be read as a direction forecast; look-ahead in data | D9, 4.5 |
| 5 | The ±1σ move was never checked against reality | G8, 4.4, 5.2 |
| 6 | Phase 2 tools only repeated data already in the prompt | 4.9, Q1 (your decision) |
| 7 | Agents got the full JSON, all model scores included | 4.5 (agent view) |
| 8 | Goals were feature checks, not outcomes | 1.2 |
| 9 | "GARCH is deterministic, tests pin this" was not true | 5.1 |
| 10 | Normal-error GARCH only | D3 (variants tested offline) |
| 11 | No schema version, no timing logs, duplicate concurrent work | 4.5, 4.10 |
| — | Wrong test counts; summary text assumed per-request choice; LangGraph conflict with `REBUILD_PLAN.md`; live-check model unstated | 1.4, 4.8, D4, 5.3 |

---

## 1. Plan

### 1.1 Problem

Bull vs Bear gives an LLM a few prices, ratios and news headlines and asks it to argue. The numbers it reasons about
are whatever the model makes of them. We want the agents to use **measured quantitative evidence**, and we want to be
able to say, with numbers, how good that evidence is and whether the agents use it correctly.

### 1.2 Goals

Feature goals say the thing exists; outcome goals say it works. Both are needed.

| # | Goal | Type | How we will know |
|---|---|---|---|
| G1 | Agents receive a volatility forecast (size of likely moves) | feature | `quant` present in the agents' data for a normal ticker |
| G2 | The forecast's track record against simple baselines is available | feature | Track record in the UI view |
| G3 | No direction claim of any kind reaches the agents | feature | Agent view has no direction forecast and no base rate (D9) |
| G4 | Agents can choose what to look at (only if Phase 2 goes ahead, Q1) | feature | Tool calls happen within the cap |
| G5 | The human sees the numbers | feature | Volatility card rendered |
| G6 | Quant failure never breaks the debate | feature | Tests in 5.1 |
| G7 | **Agents quote the numbers correctly** | outcome | At least 95% of quoted quant numbers match the block in the live check (5.3) |
| G8 | **The stated range is honest** | outcome | Share of real 21-day moves inside the ±1σ range is between 60% and 76% (target 68%) on held-out data (5.2) |
| G9 | **The chosen model beats the naive guess on unseen data** | outcome | Held-out test in 5.2 passes |

### 1.3 Non-goals

- Forecasting price direction or returns.
- Trading signals, portfolio construction, back-tested returns.
- Replacing the Bull, Bear, Judge structure.
- Supporting non-US markets in the first version (not blocked, not tested).

### 1.4 Current state (facts from the repository)

- Pipeline: `fetch_data` then Bull and Bear in parallel then Judge (LangGraph, `src/graph.py`).
- Tests at the last commit: 75 backend (pytest) and 11 frontend (vitest), all with a fake LLM. The model has never
  been run end to end on a live provider.
- Data: yfinance (price, ratios) and DuckDuckGo (news), cached 5 minutes.
- Agents receive an evidence block as text and cannot call anything. The verdict is parsed from free text.
- **A prototype exists in the working tree, uncommitted, written before this design:** `src/tools/quant.py`, a history
  fetcher, prompt text, an API field, 24 new backend tests (99 in total), `scripts/eval_quant.py`, and one measured
  result. Section 6 says what to keep, change or drop.

### 1.5 What the prototype measured, and how much it proves

On 24 large US stocks, about 35 test months each (`eval/results/quant-2026-11-09.json`), average error (QLIKE)
versus the naive guess "next month equals last month": one-year average 36% lower, GARCH(1,1) 34% lower, EWMA 20%
lower. GARCH did not beat the one-year average.

Limits of this evidence, stated wherever the numbers are used:

- **About 35 independent periods, not 839.** The stocks share the same calendar months and move together, so the
  pooled count overstates the evidence.
- **Survivorship bias.** The tickers are today's large companies. Stocks that collapsed or were delisted, often the
  hardest to forecast, are missing.
- **Same data for choosing and reporting.** Nothing was held out.
- **One period (mostly 2021 to 2026), one data source, one run.**
- **Adjusted prices.** yfinance adjusts past prices for later splits and dividends (`auto_adjust=True`, checked).

Conclusion carried into the design: the safe claim today is "volatility models beat a naive guess on this sample",
pending the held-out test in 5.2. "GARCH beats simple methods" is not supported.

---

## 2. Architecture decisions

### D1. Which target do we forecast?

| Option | Verdict |
|---|---|
| Price or return direction | Rejected: cannot be done honestly |
| Return magnitude (volatility) | **Chosen**: it clusters, so it is forecastable and testable |
| Value-at-risk or drawdown probability | Later, derived from volatility, only after G8 passes |

### D2. How do agents get the numbers?

| Option | For | Against |
|---|---|---|
| A. A short summary pre-fetched into the prompt | Simple, works with every model | Agents cannot choose |
| B. Agents call tools during their turn | Real tool use | Needs tool-calling support; more latency and failure modes; only useful if tools offer real choices (4.9) |
| C. A, plus B for real choices | Robust and richer | Most code |

**Choice: A now. B only if you choose it in Q1.** Local Ollama models such as gemma3 do not support native tool
calling reliably, so B would be Gemini-only at first, with A as the fallback.

### D3. Which volatility models, and how is the default chosen?

**Candidates.** Baselines: naive (last 21 days), one-year average (last 252 days), EWMA (lambda 0.94). Models:
GARCH(1,1) with normal errors, GARCH(1,1) with Student-t errors, GJR-GARCH(1,1) (reacts more to falls than rises).
The variants are tried in the offline evaluation only; none reaches the request path unless it wins under the rule
below. No LSTMs or Transformers: too many parameters for one stock's daily series, and no evidence of benefit.

**Choosing the default: decided once, offline, on held-out data.**

1. **Split by time.** The evaluation uses **10 years** of history (not 5), because the first test date needs a
   2-year warm-up. Choose using test dates up to 2023-11-30 (the "selection period", about 2018 to 2023, which includes
   the 2020 crash). Report using test dates from 2024-01-02 (the "held-out period"), which play no part in the choice.
   Selection dates stop a month early so no selection window reaches into the held-out period.
   *(v2 said 2021 to 2024 and 2025 to 2026; that was not possible with 5 years of data. Changed on 2026-11-09.)*
2. **Compare within each stock.** For each stock, the ratio `model QLIKE / best-baseline QLIKE`. Summarise with the
   **median ratio** across stocks, so a few volatile stocks cannot dominate.
3. **Test for significance across time, not across stocks.** For each test month, average the loss difference across
   all stocks (one number per month), then run a Diebold-Mariano test (with Newey-West standard errors) on that
   monthly series. This respects that stocks move together.
4. **Rule, written before looking:** a model replaces the best baseline as default only if, in the selection period,
   its median ratio is at most 0.95 **and** the Diebold-Mariano test favours it at the 5% level. Otherwise the best
   baseline is the default.
5. **Report** the chosen default's held-out results (G9) and calibration (G8), whatever they are.

The per-stock track record is shown to the human as information. It never chooses the model at request time.

### D4. Orchestration

Keep LangGraph for this work. It earns its place only if Phase 2 adds a tool loop. If you drop Phase 2 (Q1), the
graph stays a fixed four-step pipeline, and `REBUILD_PLAN.md`'s suggestion (plain `asyncio`) applies to any future
rewrite. Either way, changing the orchestrator is out of scope here.

### D5. Where does market data come from?

Keep yfinance, behind one function (`get_price_history`). It scrapes Yahoo and fails intermittently (XOM failed once,
then worked). Mitigation: cache, retry once, treat failure as "no quant block". A licensed API later is a one-file change.

### D6. Caching

| Data | TTL | Why |
|---|---|---|
| Price history (5 years of daily closes) | Q4: 5 minutes (today) or 1 hour (proposed) | End-of-day data changes once a day |
| Today's forecast for a ticker | 1 hour | One GARCH fit; cheap, but no reason to repeat |
| Per-stock track record | 24 hours | Computed in the background (D8) |
| Concurrent identical requests | single-flight | Two requests for the same ticker share one computation (4.10) |

### D7. Security and trust

- The ticker is fixed by the request and validated by the existing regex. Tools take no free-text arguments
  (4.9), so injected news text cannot steer a lookup.
- Tool output is numbers from our code, not web text. It still sits inside the `<data>` block.
- Tool calls are capped.

### D8. What runs per request, and what runs elsewhere (new)

| Work | Where | Cost |
|---|---|---|
| Download history, compute today's forecast with the default model, regime, ±1σ range | Per request (cached 1 h) | One fit, about 70 ms plus the download |
| Per-stock walk-forward track record and calibration | Background task after a cache miss, cached 24 h; the first request shows "track record pending" | About 2 to 3 s, off the request path |
| Multi-stock evaluation, default-model choice | Offline script (`scripts/eval_quant.py`), run by hand or weekly in CI | Minutes |

This removes the walk-forward from the request path, which was most of the prototype's latency.

### D9. Data integrity (new)

| Risk | Rule |
|---|---|
| Unfinished trading day in the last row | Drop the last row if its date is today in New York time and the US market has not closed. Test it. |
| Price adjustments use later information | Accept and document. The effect on volatility is small (dividend adjustments scale prices, not returns, except on ex-dividend days). |
| Survivorship | Reduce it in the evaluation (5.2). It cannot be removed with yfinance, which does not serve most delisted tickers. |
| Direction leakage | The base rate "share of months up" stays out of the agent view. The UI may show it, labelled "past base rate, not a forecast". |

---

## 3. High-level design (HLD)

### 3.1 Component view

```
                      Browser (React)
                      - ticker input, progress, argument cards
                      - NEW: volatility card (Phase 3)
                              |  POST /api/debate/stream (SSE)
                              v
   FastAPI (src/api.py)  -- rate limit, key header, whitelist of response fields
                              |
                              v
   LangGraph pipeline (src/graph.py)
   +------------------------------------------------------------------+
   | fetch_data  --->  bull_agent  ---+                               |
   |   (price, ratios,  (Phase 2,     |-->  judge_agent  --> memo      |
   |    news, quant)     if chosen)   |                                |
   |             ---->  bear_agent ---+                                |
   +------------------------------------------------------------------+
        |                     \
        v                      \  (cache miss) schedule
   src/tools/                   v
     market_data.py         background track-record task (D8)
     news.py                   |  writes 24 h cache
     quant.py  <---------------+
        |
        v
   External: Yahoo Finance, DuckDuckGo, Gemini or Ollama

   Offline: scripts/eval_quant.py --> eval/results/*.json --> QUANT_DEFAULT_MODEL
```

### 3.2 Data flow (Phase 1, per request)

1. Browser sends the ticker; API validates and rate-limits.
2. `fetch_data` fetches price and ratios, then runs news search and quant in parallel (both wait on the network).
3. Quant: get history, drop an unfinished day, compute returns, today's forecast with `QUANT_DEFAULT_MODEL`, regime,
   ±1σ range. Read the track record from cache; if missing, schedule the background task and mark it pending.
4. State holds the full block; agents get the **agent view**, the browser gets the **UI view** (4.5).
5. Judge's memo returns; the API streams the whitelisted result over SSE.

### 3.3 Data flow (Phase 2, only if Q1 chooses it)

Bull and Bear each run a capped loop: model turn, optional tool calls, results, final argument. The agent view stays
in the prompt; tools give choices the summary does not contain (4.9).

### 3.4 Failure behaviour

| Failure | Behaviour |
|---|---|
| History missing or under about 2.2 years | No quant block; debate continues |
| Default model fails on today's data | Fall back to the best baseline; note it in the block |
| Track record not yet computed | Block says "track record pending"; forecast still shown |
| Background task fails | Logged; retried on the next cache miss; never affects a request |
| Tool call errors (Phase 2) | Tool returns "unavailable"; agent argues without it |
| Model without tool support (Phase 2) | Agent view only |
| Yahoo down | Existing behaviour: 503 if price fails; quant simply absent |

### 3.5 Non-functional targets (all to be measured in Phase 4, not assumed)

| Item | Target |
|---|---|
| Added latency, cold | Under 1.5 s beyond the history download, in parallel with news |
| Added latency, warm | Under 100 ms |
| Prompt tokens added per agent | Under 250 (agent view only); measured with the provider's token counter |
| Reproducibility | Same history gives the same forecast to 4 decimal places; a test checks it |
| Compatibility | Existing API fields unchanged; one new field `quant`, with `schema_version` |

---

## 4. Low-level design (LLD)

### 4.1 Modules

| Module | Status | Responsibility |
|---|---|---|
| `src/tools/market_data.py` | edit | `get_price_history(ticker, years=5)`; drops an unfinished trading day |
| `src/tools/quant.py` | rework prototype | Pure maths; `forecast_today(ticker)`; `track_record(ticker)` for the background task; `agent_view()`, `ui_view()` |
| `src/tools/quant_jobs.py` | new | Background track-record task and its 24 h cache, single-flight |
| `src/agents/nodes.py` | edit | `fetch_data_node` adds `quant`; `format_data` uses the agent view |
| `src/agents/prompts.py` | edit | `_QUANT` paragraph, rewritten for the agent view |
| `src/agents/tools.py` | new, Phase 2 only | Tool definitions (4.9) |
| `src/api.py` | edit | `quant` (UI view) in the response whitelist and initial state |
| `src/config.py` | edit | Settings (4.7) |
| `scripts/eval_quant.py` | rework prototype | The evaluation in 5.2; prints the D3 decision |
| `frontend/src/components/VolatilityCard.jsx` | new, Phase 3 | Display |

### 4.2 Key definitions

- Log returns `r_t = ln(P_t / P_{t-1})`.
- Target: average daily variance over the next `H = 21` trading days, measured as the mean of squared returns.
- Annualized volatility % `= sqrt(daily_variance * 252) * 100`.
- QLIKE loss `= x - ln(x) - 1`, `x = realized / forecast`. Zero when perfect; penalises under-forecasting more.
- RMSE in annualized percentage points, as a readable second measure.
- ±1σ range over the horizon: `± forecast_vol * sqrt(H / 252)`, applied to the log return over the next `H` days.

### 4.3 Models

| Name | Definition |
|---|---|
| `naive` | Mean square of the last 21 returns |
| `long_run` | Mean square of the last 252 returns |
| `ewma` | `v_t = 0.94 v_{t-1} + 0.06 r_t^2`, seeded from the first 21 returns of the window; flat forecast |
| `garch` | GARCH(1,1), zero mean, normal errors, on the latest 1,000 returns in percent; average the `H`-day forecast path; reject if not converged |
| `garch_t`, `gjr` | As `garch` with Student-t errors / with the GJR asymmetry term. Offline evaluation only, unless chosen by D3 |

Every model receives only `returns[:t]`; a test enforces it.

### 4.4 Walk-forward procedure and calibration

Runs in the background task (per stock) and in the offline script (many stocks). Never on the request path.

```
for t in range(504, n - H + 1, 21):           # first test date after 2 years; windows do not overlap
    realized_var = mean(r[t : t+H]^2)
    move = sum(r[t : t+H])                     # the actual log move over the window
    forecasts = {model: f(r[:t])}              # may raise
    if any failure, non-positive value, or realized_var == 0: drop t for ALL models
    record per model: QLIKE, vol error,
                      inside_1sigma = |move| <= sqrt(forecast * H),
                      inside_2sigma = |move| <= 2 * sqrt(forecast * H)
    record the test date, so results can be grouped by month (5.2)
```

Calibration per model is the share of test dates inside each band (G8). Minimum history: 546 returns.

### 4.5 Output: one block, two views

Full block, kept in state. `schema_version` changes whenever a field is renamed or removed.

```json
{
  "schema_version": 1,
  "as_of": "2026-11-06",
  "horizon_trading_days": 21,
  "volatility": {
    "model": "long_run",
    "fallback_used": false,
    "forecast_annualized_pct": 31.4,
    "one_sigma_move_over_horizon_pct": 9.1,
    "current_pct": 28.0, "percentile_1y": 41, "regime": "normal"
  },
  "track_record": {
    "status": "ready | pending | unavailable",
    "test_dates": 35, "skipped": 0,
    "scores": {"naive": {"qlike": 0.0, "rmse_vol_pts": 0.0}, "...": {}},
    "calibration": {"inside_1sigma_pct": 0, "inside_2sigma_pct": 0},
    "summary": "one sentence, see 4.8"
  },
  "price": {"return_1m_pct": 0, "return_3m_pct": 0, "return_6m_pct": 0, "max_drawdown_1y_pct": 0,
            "past_months_up_pct": 0},
  "caveats": ["..."]
}
```

| View | Sent to | Contents |
|---|---|---|
| **Agent view** | Bull, Bear, Judge (inside `<data>`) | `forecast_annualized_pct`, `one_sigma_move_over_horizon_pct`, `regime`, `percentile_1y`, recent returns and drawdown, the summary sentence, the first caveat. **No model scores, no `past_months_up_pct`.** |
| **UI view** | Browser | Everything above, with `past_months_up_pct` labelled "past base rate, not a forecast" |

Error shape (never raised past the node): `{"error": "message", "kind": "insufficient_data | bad_data | not_found | failed"}`.

### 4.6 State and API changes

- `AgentState` gains `quant: Dict[str, Any]` (total=False).
- `format_data` adds the **agent view** inside `<data>...</data>`; the existing closing-tag neutralisation still applies.
- `build_result` adds the **UI view** as `quant`. The API key-set test changes by one name.
- The `fetch_data` SSE `stage` event already carries `build_result`, so the card renders before the agents answer.

### 4.7 Configuration

| Setting | Default | Meaning |
|---|---|---|
| `QUANT_ENABLED` | true | Turn the feature off |
| `QUANT_HORIZON_DAYS` | 21 | Forecast horizon |
| `QUANT_DEFAULT_MODEL` | from the D3 decision | Model used at request time |
| `QUANT_FORECAST_TTL_SECONDS` | 3600 | Today's forecast cache |
| `QUANT_TRACK_RECORD_TTL_SECONDS` | 86400 | Background track-record cache |
| `QUANT_MAX_TOOL_CALLS` | 3 | Phase 2 cap per agent |

### 4.8 Summary sentence (generated by code, not the LLM)

The default is fixed by D3, so the sentence describes the default's record for this stock against the baselines.

| Situation | Sentence |
|---|---|
| Track record pending | "Forecast from the <model> method. Its track record for this stock is still being computed." |
| Fewer than 12 test dates | "Forecast from the <model> method. Too little history (N months) to score it for this stock." |
| Default beat the naive guess for this stock | "Forecast from the <model> method. On this stock's past N months it had X% lower error than the naive guess; real moves fell inside the ±1σ range in Y% of months (68% expected)." |
| Default did not beat the naive guess for this stock | "Forecast from the <model> method. On this stock's past N months it did not beat the naive guess; treat it with caution." |
| A fallback was used | Prefix: "The usual method failed today, so a simple average was used." |

### 4.9 Phase 2 tools (only if Q1 chooses option A)

Tools take **only enumerated arguments**, so no text from the web can steer them.

| Tool | Arguments | Returns |
|---|---|---|
| `get_volatility` | `horizon_days`: one of 5, 21, 63 | Forecast and ±1σ range for that horizon (the prompt only has 21) |
| `compare_with_peer` | `peer`: one of a fixed list of 3 to 5 same-sector tickers, built by code from a static sector table | Both stocks' volatility, regime and 3-month return |
| `get_drawdown_history` | `years`: one of 1, 3, 5 | Worst drawdown and recovery time in that window |

Loop rules: at most `QUANT_MAX_TOOL_CALLS` per agent; 10 s per call; tool errors return `{"unavailable": true}`;
after the cap the agent is told to answer. Calls made are stored in state (`bull_tool_calls`, `bear_tool_calls`).

**Success measure, decided before building:** in the live check, with tools versus without, (a) quote accuracy (G7)
does not fall, and (b) at least half of the debates use a tool result in the final argument. If either fails, the
tools are removed.

To verify before coding: tool binding in `langchain-google-genai` 4.x and LangGraph's prebuilt tool node; extending
the test fake to emit tool calls.

### 4.10 Operational details

- **Single-flight:** concurrent requests for the same ticker wait on one computation (a per-key lock around the cache
  miss). The prototype's cache allows duplicate work.
- **Logging:** one structured line per request with `ticker`, `quant_ms`, `model`, `fallback_used`,
  `track_record.status`, and per background run `test_dates`, `skipped`, `run_ms`.
- **Phase 3 card:** forecast, ±1σ monthly move, regime with percentile, the summary sentence, calibration, a
  "details" toggle with all model scores, and the base rate with its label. States: loading, hidden when missing,
  "track record pending". Text only.

---

## 5. Test and evaluation plan

### 5.1 Unit and integration tests (offline, deterministic)

| Test | Protects |
|---|---|
| Hand-computed naive, one-year, EWMA, annualize, QLIKE, ±1σ band | The maths |
| QLIKE is 0 when perfect and larger for under-forecasting | The loss |
| **Forecasts unchanged when data after the forecast date is altered** | No look-ahead |
| A failed model drops the date for all models | Fair comparison |
| Test-date count equals the expected range | No off-by-one |
| **Same history gives the same GARCH forecast to 4 decimals across two runs** | Reproducibility (replaces the v1 claim) |
| **Unfinished trading day is dropped; a finished one is kept** | D9 |
| Calibration: on a simulated series with known variance, about 68% inside ±1σ | The calibration code |
| **Agent view contains no model scores and no `past_months_up_pct`** | G3 |
| `schema_version` present; UI view JSON-serialisable | API contract |
| Default model from config is used; fallback on failure is flagged | D3, 3.4 |
| Single-flight: two concurrent misses compute once | 4.10 |
| Quant exception or error result never stops the debate | G6 |
| Agent view reaches the Judge's prompt; prompts say "not a direction forecast" | G1, G3 |
| Phase 2 only: cap, tool error, enumerated-argument validation, model without tools | G4, G6, D7 |

### 5.2 Offline evaluation (decides the default and reports G8, G9)

1. **Tickers.** At least 40, in three groups: large caps across sectors; mid caps; and stocks that fell at least 50%
   from their peak during the period (chosen by that rule, not by hand). This reduces survivorship bias; it cannot
   remove it.
2. **Periods.** Selection: origins up to 2023-11-30; held-out: origins from 2024-01-02 (D3). Ten years of prices per
   stock, cached in `eval/cache/prices` so the run can be repeated without the network. Stocks that listed late have
   fewer dates; a stock counts in a period only with at least 12 scored dates there.
3. **Per model:** median per-stock QLIKE ratio versus the best baseline; mean QLIKE; RMSE; calibration (inside ±1σ
   and ±2σ); results per ticker group.
4. **Significance:** Diebold-Mariano on the monthly cross-stock mean loss difference, Newey-West standard errors.
5. **Decision:** apply the D3 rule to the selection period; write `QUANT_DEFAULT_MODEL` and the reason into the
   results file; report the held-out results whatever they are.
6. **Output:** `eval/results/quant-<date>.json` plus a short Markdown summary; the README quotes only held-out numbers.

### 5.3 Live check (needs a key; not done yet)

- **Model:** Gemini, if you provide a key (Q3); otherwise Ollama with the local default model, reported as such.
  Results are only claimed for the model they were run on.
- **Runs:** 10 tickers, recording latency, prompt tokens and verdict.
- **Quote accuracy (G7):** each agent ends its argument with a short machine-readable list of the quant numbers it
  used (`{"field": ..., "value": ...}`), required by the prompt. A script compares them with the block. Number-matching
  in free text is not used; it is too fragile.
- **Phase 2 comparison** (only if built): the same 10 tickers with and without tools (4.9 success measure).

---

## 6. Phases, exit criteria, and what happens to the prototype

| Phase | Work | Exit criteria |
|---|---|---|
| 0 | Approve this document; answer Q1 to Q8 | Your sign-off |
| 1a | Offline evaluation per 5.2 | D3 decision recorded; G8 and G9 reported on held-out data |
| 1b | Request path per D8, D9 and 4.5 (agent and UI views) | Tests in 5.1 pass; latency measured locally; README quotes held-out numbers only |
| 2 | Agent tools, only if Q1 says so | 4.9 success measure met, or tools removed |
| 3 | Volatility card | Renders from the SSE stage; hidden when missing; pending state works |
| 4 | Live check | G7 measured; latency and token numbers recorded |

Phase 1a comes first because its result decides the default model and whether the claims hold at all.

**Prototype disposition (your decision, Q5):**

| Piece | Keep | Change | Drop |
|---|---|---|---|
| Maths, walk-forward, leakage and failure tests | yes | add calibration, dates per test point | |
| Per-request walk-forward and per-request model choice | | move to the background task; use the configured default | |
| `share_of_months_up_pct` in the agent prompt | | rename `past_months_up_pct`, UI view only | |
| Full JSON in the prompt | | agent view | |
| `eval_quant.py` and the 2026-11-09 result | yes, the result as a superseded first run | rework per 5.2 | |
| Prompt paragraph, API field, node wiring, `arch` and `scipy` | yes | prompt rewritten for the agent view | |

---

## 6a. Phase 1a result (2026-11-09)

Run: `scripts/eval_quant.py`, 60 stocks, files in `eval/results/quant-2026-11-09.{json,md}`.

| Item | Result |
|---|---|
| D3 rule outcome | **GJR-GARCH** is the default (selection median ratio 0.923 vs EWMA, p = 0.044) |
| G8, range is honest | **Met**: 69.0% inside ±1σ, 94.9% inside ±2σ on held-out data |
| G9, beats naive on unseen data | **Met**: median ratio 0.60, p < 0.0001 |
| Shipped default (one-year average, Q9) | G8: 67.1% inside ±1σ, 93.8% inside ±2σ. G9: median ratio 0.613 vs naive, p = 0.0024. Both met. The first version of this table quoted GJR's figures; corrected 2026-11-09 |
| Robustness | The rule's pass was narrow (GARCH-t: p = 0.065). The best baseline flipped from EWMA (selection) to the one-year average (held-out). GJR vs the one-year average on held-out data: ratio 0.968, p = 0.075, **no significant edge** |

Consequence for the design: the claim stays "volatility is forecastable better than a naive guess, with an honest
range". D3's rule fixes the baseline from the selection period only; this run shows that can favour a baseline that
loses later. If you want the rule to be more robust, amend it before Phase 1b (for example, require the candidate to
beat the best baseline in each of two sub-periods). See Q9.

## 6b. Phase 1b: what was built, and where it differs from this design

| Item | Design said | Built | Why |
|---|---|---|---|
| Default model | Set by the D3 rule (GJR) | **One-year average** (`long_run`) | Q9 answered: GJR passed narrowly and is not significantly better than the one-year average on held-out data |
| Track record (D8) | Background task, `pending` status | **Inline**, status `ready` or `unavailable` | The default is a baseline: about 16 ms. The background job was not worth its code. `pending` is never produced |
| `arch`, `scipy` | Request-path dependencies | **Dev-only** (`requirements-dev.txt`) | The request path does not import them; smaller Docker image |
| Settings | Six `QUANT_*` settings | Four: `QUANT_ENABLED`, `QUANT_DEFAULT_MODEL`, `QUANT_FORECAST_TTL_SECONDS`, `PRICE_HISTORY_TTL_SECONDS` | `QUANT_HORIZON_DAYS` would need the horizon to be a parameter everywhere; no track-record TTL without a separate cache |
| `direction` field in the block | Not in the 4.5 schema | Removed from the block (the prototype had `direction.forecast = null`) | The first caveat and the prompt already say it |
| Cache lifetime (Q4) | 1 hour | 1 hour, for both history and forecast | As recommended |

Measured on live data (2026-11-09): compute 16 ms (default), 1.1 s (GJR), 2.6 s (GARCH); AAPL cold request 2.6 s and NVDA 0.9 s including
the Yahoo download; agent view about 170 tokens (characters / 4). Targets in 3.5 are met for the default model.

Still to do: Phase 3 (volatility card), Phase 4 (live-model check, quote accuracy G7).

## 7. Open questions for you

| # | Question | My recommendation |
|---|---|---|
| Q1 | Phase 2: **(A)** build agent tools with real choices (4.9) and the success measure, or **(B)** drop Phase 2 and keep the pre-fetched summary only | **B for now.** The project gains more from Phases 1a and 4 (honest, measured numbers) than from tool use. Revisit A after the live check shows how agents use the summary. If the aim is to show agent tool use on your resume, choose A. |
| Q2 | Approve the D3 rule (time split, median ratio, Diebold-Mariano, 0.95 threshold)? | Yes |
| Q3 | Do you have a Gemini API key for the live check, and accept the rate limits? | Yes. Free-tier quotas are small and change, so plan only a handful of runs |
| Q4 | Raise the price-history cache to 1 hour? | Yes; daily closes do not change intraday once D9 drops the unfinished day |
| Q5 | Accept the prototype disposition table? | Yes |
| Q6 | `decision.md` entries 19 to 25 describe the prototype as settled. Reword them as "prototype, pending this design"? | Yes, after approval |
| Q7 | Expand the evaluation to 40+ tickers including mid caps and stocks that fell 50%+ (longer runs, more Yahoo calls)? | Yes |
| Q8 | Background track-record task (D8), or show no per-stock track record at all and only the offline results? | Background task; per-stock numbers are what the human wants to see |
| Q9 | Phase 1a picked GJR-GARCH by the written rule, but only narrowly, and it is not significantly better than a plain one-year average on held-out data. Keep GJR (the rule's output), switch the default to the one-year average (simpler, no model fit), or amend the rule first? | One-year average as the request-path default, with GJR shown as an alternative. The honest claims (G8, G9) hold for both, and the simpler method has nothing to overfit. Keeping GJR is also defensible because the rule was written in advance. |
