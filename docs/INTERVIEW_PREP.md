# Interview prep: Bull vs Bear

Answers use only what is measured (`decision.md`, `eval/results/quant-2026-11-09.json`). If a question goes past that,
say what was not measured; that is a stronger answer than a guess.

## The project in 30 seconds
A multi-agent app (LangGraph): data is fetched first, a Bull and a Bear agent argue in parallel, a Judge decides. It is a
fixed workflow, not an autonomous agent. I added a volatility forecast the agents can read, and evaluated it properly.

## Questions

**Why volatility and not price?**
Volatility clusters (calm months follow calm months), so it can be forecast and tested. Price direction cannot be
forecast honestly with this data. The tool says how big a move may be, never which way, and the code carries no direction field.

**Why a one-year average and not GARCH?**
I set a selection rule in advance and tested on a later period the models never saw. GJR-GARCH was 3% better than the
one-year average but not significantly (p = 0.075). The best simple method also changed between periods. A simpler method
that is as good is cheaper, faster (16 ms against 1 to 3 s) and needs no fitting. The rule picked GJR narrowly (p = 0.044)
and I overrode it, and wrote down why.

**How do you know it works?**
Median error 39% below the naive guess (next month equals last month) across 60 stocks on 34 months it never saw
(p = 0.0024). The stated ±1σ range held 67.1% of real moves (68% expected) and ±2σ 93.8% (95% expected).

**Why that significance test?**
Stocks move together, so 60 stocks x 34 months are not 2,040 independent observations. I averaged losses across stocks per
month and used Diebold-Mariano with Newey-West errors on those 34 monthly differences.

**What about look-ahead?**
A test changes all data after the forecast date and checks the forecast does not move. Test windows do not overlap, and a
date is dropped for all models if any model fails on it.

**What are the weaknesses?**
Survivorship (only stocks that still trade), prices adjusted for later splits and dividends, about 34 independent months,
one data source (Yahoo, unofficial). None of this says the debate's verdicts are good.

**Does the tool make the verdicts better?**
Not measured. I measured the forecast, not the verdicts. The harness for consistency, position bias and faithfulness is
built (`scripts/live_eval.py`) but has not been run on a real model.

**How do agents use the numbers without misquoting?**
They get a short view (forecast, typical move, regime, recent returns, one sentence written by code). Model scores and the
past-months-up rate are withheld because they are easy to misquote or read as a probability of a rise. Whether they still
misquote is what the faithfulness check will measure.

**What would you do with more time?**
Run the live evaluation, publish the numbers even if poor, then try a rebuttal round only if consistency is weak.

**What did you get wrong along the way?**
I started coding before a design and stopped. I quoted GJR's calibration for the model that ships; I found it on review,
fixed the script that checked goals against the wrong model, and logged it (decision 36).

**How does closing the tab save money?**
A cancel flag is checked before every model call and the stream pings every 5 s so a closed connection is noticed. In a
test against a real local server, Bull and Bear (already running) finished and the Judge was never called. In-flight
calls are not aborted.

**How is the demo mode protected from abuse?**
Per-visitor and total daily caps, a failed lookup is refunded, the server key never reaches the browser, and the client
address comes from the Nth entry from the right of `X-Forwarded-For` so a forged header does not help. Limits: counts are per
process, and I would also set a spend limit on the key.

## Do not say
Predicts or beats the market; BUY/SELL/HOLD accuracy; in production; real users; any live-model result; works with Gemini
(only fake models so far); CI passing (not pushed).
