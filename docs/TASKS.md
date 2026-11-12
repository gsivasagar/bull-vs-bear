# Bull vs Bear: final goal and task breakdown

Written 2026-11-09. Status column added later the same day (see section 6). Nothing is committed or pushed.
Sources: `docs/DESIGN_QUANT_AND_AGENT_TOOLS.md`, `decision.md`, and the Bull vs Bear sections of `../IMPROVEMENT_PLAN.md`
(items 2.11 to 2.17 and the feature table). Effort: **S** under half a day, **M** 1 to 2 days, **L** 3 or more.
"You" means the task needs your accounts, keys or approval. "Me" means I can do it once you say go.

## 1. The final goal

> Bull vs Bear is a **live, current, measured** project: anyone can open the public link and run a debate without
> supplying a key; the numbers it shows are backed by evidence in the repository; the AI parts (verdict quality,
> consistency, faithfulness) are measured and the results are published, good or bad; and every claim about it on your
> resume can be traced to a file you can show.

I am assuming this is what "final goal" means. If you meant something narrower (only the quant tool) or wider (the
whole job search), say so and I will re-cut the list.

### Success criteria (the project is done when all are true)

| # | Criterion | Check |
|---|---|---|
| S1 | The public site runs the current code, at a stable URL | Open the link; the volatility card appears |
| S2 | A visitor can run a debate without their own key | Demo mode works within its daily cap |
| S3 | Quant goals G1 to G3 and G5 to G9 are met (G4, agent tools, was dropped) | Design doc, section 1.2 |
| S4 | Quote accuracy: agents repeat quant numbers correctly in at least 95% of quoted figures | Live check, task C3 |
| S5 | Verdict consistency, position bias and faithfulness are measured on a live model and published in the README | Tasks D2 to D5 |
| S6 | CI is green on GitHub; the README matches the code | Tasks A2, F4 |
| S7 | Every resume claim about this project points to a file in the repo | Tasks F1, F2 |

### Out of scope (decided)

Agent tool calls (Phase 2 dropped), back-testing returns, non-US markets, any claim about investment performance, Ollama
support claims (it was never run live).

## 2. Where things stand

| Item | State |
|---|---|
| Security and reliability fixes (`26f3f5f`) | Committed locally, **not pushed**; the live site probably runs the older code |
| Quant tool: offline evaluation (Phase 1a) and request path (Phase 1b) | **Done**, 141 tests pass, **not committed** |
| Volatility card in the web page (Phase 3) | Not started |
| Any run against a real language model | **Never done**: all tests use a fake model |
| Default model | `gemini-2.0-flash` was retired; now `gemini-2.5-flash` |

## 3. Tasks

### Workstream A: Ship what exists

| ID | Task | Depends on | Who | Effort | Done when |
|---|---|---|---|---|---|
| A1 | Commit the current work in logical commits (quant tool, evaluation, docs). Decide the policy for `eval/cache` (8.4 MB; I suggest committing prices, ignoring records) | none | Me prepare, you approve (git writes run outside the sandbox) | S | Working tree clean |
| A2 | Push `main` (includes `26f3f5f`); watch CI | A1 | You | S | CI green on GitHub |
| A3 | Check the default Gemini model still answers; bump it if retired (2.11) | C1 | Me | S | A live call succeeds |
| A4 | Redeploy backend and frontend; confirm the live site runs the new code; use the stable production URL, not a per-deploy one | A2 | You | S-M | Live site shows the security fixes |
| A5 | Build the Docker image from `requirements.txt` only (no `arch`, no `scipy`) and call `/api/health` | none | Me | S | Image builds and starts |

### Workstream B: Finish the quant feature (Phase 3)

| ID | Task | Depends on | Who | Effort | Done when |
|---|---|---|---|---|---|
| B1 | `VolatilityCard`: reads `quant` from the `fetch_data` stage event; shows forecast, ±1σ monthly move, regime and percentile, summary sentence, calibration, a details toggle with model scores, and the base rate labelled "past base rate, not a forecast". States: hidden when missing, shown otherwise. Vitest tests | none | Me | M | Card renders in the dev server; tests pass |
| B2 | Fix currency and market-cap formatting (2.14); the card shows numbers in the same page | none | Me | S | Non-USD ticker shows its currency |
| B3 | Optional: a manual or weekly CI job that re-runs `scripts/eval_quant.py` and keeps results versioned | A2 | Me | S | Job runs and uploads results |

### Workstream C: First contact with a real model (needs your key)

| ID | Task | Depends on | Who | Effort | Done when |
|---|---|---|---|---|---|
| C1 | Give me a Gemini key through an environment variable, never in a file, and set a spend or quota limit on it | none | You | S | Key works in a one-line test |
| C2 | First end-to-end run on 10 tickers; record latency, prompt tokens, errors and verdicts | C1, A3 | Me | M | Table saved in `eval/results/` |
| C3 | Quote accuracy (G7): each agent ends with a machine-readable list of the quant fields it used; a script compares them to the block. Target: at least 95% match | C2 | Me | M | Measured percentage recorded |
| C4 | If C3 is below target, fix the prompts and measure again | C3 | Me | S-M | Target met, or the shortfall is documented |
| C5 | Write the results into the README and `decision.md` | C2 to C4 | Me | S | Both updated |

### Workstream D: Debate quality (the AI part, currently unmeasured)

| ID | Task | Depends on | Who | Effort | Done when |
|---|---|---|---|---|---|
| D1 | Structured Judge output: a schema with recommendation, confidence, key reasons, risks and cited figures, replacing the free-text parsing (2.16). Keep the text memo for display | none | Me | S-M | Parser removed; tests updated |
| D2 | Faithfulness: check in code that every number an agent cites exists in the fetched data | C3, D1 | Me | M | Share of correct figures measured |
| D3 | Consistency: same ticker five times; how often the verdict flips | C1, D1 | Me | M | Flip rate recorded for 10 tickers |
| D4 | Position bias: swap the order Bull and Bear are shown to the Judge; how often the verdict changes | C1, D1 | Me | M | Change rate recorded |
| D5 | Publish the D2 to D4 table in the README, including bad results | D2 to D4 | Me | S | Table is in the README |
| D6 | Optional: one rebuttal round, toggleable, and measure whether it changes verdicts | D3, D4 | Me | M | Effect and latency cost reported |
| D7 | Optional: a better news query using the company name, dedupe, drop old items (2.17) | none | Me | S | Short tickers return relevant news |

### Workstream E: Reliability, security, cost

| ID | Task | Depends on | Who | Effort | Done when |
|---|---|---|---|---|---|
| E1 | Rate limit by the client address behind a proxy (2.12) | none | Me | S | Per-visitor limit verified |
| E2 | Stop the debate when the browser tab closes (2.13) | none | Me | M | A closed tab stops model calls |
| E3 | Demo mode: a server-side key, a cheap model, per-visitor and global daily caps, three cached example debates (2.15). Needed so recruiters can see it run | A4, C1, E1 | Me build, you set the key and cap | M | Site works with no visitor key until the cap |
| E4 | Show tokens and cost per debate in the response and the page | C2 | Me | S-M | Numbers shown and tested |

### Workstream F: Resume and interview

| ID | Task | Depends on | Who | Effort | Done when |
|---|---|---|---|---|---|
| F1 | Add the Bull vs Bear numbers and how to defend them to `resume/NUMBERS_AND_HOW_TO_DEFEND_THEM.md`; fix anything now stale there | A1 (quant numbers); C5, D5 for AI claims | Me | S | File updated |
| F2 | Write the resume bullet or bullets with only defensible claims; update the master and tailored resumes | F1 | Me draft, you approve | S | Bullets approved |
| F3 | Interview prep: why volatility and not price, why the one-year average, survivorship, the significance test, calibration, what was not measured | F1 | Me | S | Questions and answers written |
| F4 | Final README pass and a short demo GIF | A4, B1 | Me, you record the screen if needed | S-M | README matches the live site |

## 4. Order of work

| Milestone | Tasks | What you get |
|---|---|---|
| M1 Visible | A1, A5, A2, A4 | Current code is public; CI green |
| M2 Complete quant | B1, B2 | Volatility card on the page |
| M3 First live evidence | C1, A3, C2, C3, C4, C5, D1 | Real latency, tokens and quote accuracy |
| M4 AI quality | D2, D3, D4, D5 | Published consistency, bias and faithfulness numbers |
| M5 Recruiter-ready | E1, E3, F1 to F4 | Demo mode, resume bullets, interview prep |
| Optional | B3, D6, D7, E2, E4 | After M5, if time allows |

**Critical path:** A1, A2, A4 (visibility) and C1, C2, C3 (evidence) are independent and can run in parallel.
D3 to D5 need C1 and D1. E3 and F4 need A4. F2 comes last.

**Your actions, in order of when they block something:** approve A1 commits; push (A2); give a key and set a limit
(C1); redeploy (A4); set the server key and daily cap for demo mode (E3); approve the resume bullets (F2).

## 5. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Free-tier Gemini limits are small and change | C2 to D4 need many calls (about 10 tickers, 5 repeats, 2 orders) | Plan the run counts first; use the cheapest adequate model; cache results; limit the spend on the key |
| Live results may be poor (verdicts flip, high position bias) | The README shows weak numbers | Publish them anyway; poor measured results are still a stronger signal than none; fix prompts and re-measure |
| Yahoo Finance is unofficial and fails sometimes | Flaky live runs | Retry once; cached prices for evaluation; absent quant block never breaks a debate |
| Demo mode could run up cost | Surprise bill | Hard daily cap and a spend limit on the key before E3 goes live |
| Prices are adjusted for later splits and dividends | Small effect on volatility, documented | Already listed under limits |

## 6. Status (2026-11-09, end of the first working pass)

Details and deviations for each item are in `decision.md`, entries 38 to 48.

| ID | Status |
|---|---|
| A1, A2 | **Waiting for you.** Committing and pushing need your word (standing rule). |
| A3 | **Done:** `gemini-2.0-flash` retired; default is now `gemini-2.5-flash` |
| A4 | Blocked on A2 |
| A5 | **Partly done:** the Docker daemon is not running; a clean environment from `requirements.txt` alone imported the app and answered `/api/health`. Run `docker build .` once Docker Desktop is up |
| B1, B2 | **Done** (21 frontend tests, lint, build) |
| B3 | **Done** as a manual workflow; never run on GitHub |
| C1 | **Done** (key supplied; free tier, so quota is the limit) |
| C2 | **Mostly done:** 9 of 10 debates completed (XOM failed twice); decisions 51, 56 |
| C3 | **Started:** checker bug fixed; 93 of 94 numbers found in the 3 audited debates; sample far too small (decisions 57, 58) |
| C4, C5 | Not started; need a larger audited sample |
| D1 | **Done**, verified on real Gemini (6 of 6 structured); text parser kept as a fallback |
| D2 to D4 | **Tooling done**; not run (`--plan full` is 300 calls; needs more quota) |
| D5 | Blocked on the D2 to D4 runs |
| D6 | Not started (only worth doing after D3 and D4 results) |
| D7 | **Done** (not measured against real news results) |
| E1 | **Done**; set `TRUSTED_PROXY_HOPS` at deploy time |
| E2 | **Done**, checked on a real local server (no further model calls after the tab closes) |
| E3 | **Built, off by default**; cached example debates not built; needs your key and cap |
| E4 | **Done** (tokens; cost only if prices are set) |
| F1 to F3 | See `../resume/NUMBERS_AND_HOW_TO_DEFEND_THEM.md` (updated) and `docs/INTERVIEW_PREP.md` |
| F2 | Draft bullets are in `decision.md`; **you approve** before the resume changes |
| F4 | Blocked on A4; README text is updated, no demo GIF |

### Update after the "complete the partly done 8" pass
| ID | Status |
|---|---|
| A5 | Still partial: needs Docker Desktop running (`docker build -t bvb .`); the Dockerfile copies `demo/`, which only exists after the examples run |
| C2, C3, D2, D3, D4 | **Not completed.** The medium run got 429 on every call (quota used up); see `decision.md` entry 60. Re-run after the quota resets |
| E3 | Endpoints and page buttons are built and tested; **no example data** until the run above succeeds. You still set `DEMO_API_KEY` and the caps |
| F2 | Draft only; no live-quality claims are allowed yet |
