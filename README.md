# Bull vs Bear: AI Investment Debate

An AI tool that stages a debate about a stock. A **Bull** agent argues for buying, a **Bear** agent argues against, and
a **Judge** weighs both against the underlying data and issues a BUY / SELL / HOLD memo.

> **Not financial advice.** The output is AI-generated text built from public data. It can be wrong, out of date or
> biased by the news it reads. Use it for learning and entertainment only.

## How it works

```
fetch data (price, ratios, news) ──┬──> Bull agent ──┐
                                   └──> Bear agent ──┴──> Judge ──> BUY / SELL / HOLD memo
```

- **LangGraph** runs the steps. Bull and Bear never read each other's argument, so they run **in parallel**; the Judge
  waits for both.
- **Data:** `yfinance` (price and ratios) and DuckDuckGo news search, cached for 5 minutes. News is untrusted web text:
  it is cleaned, wrapped in `<data>` tags and the agents are told to ignore instructions inside it.
- **Models:** Google Gemini (`gemini-2.5-flash`) when you enter an API key, otherwise a local Ollama model
  (`gemma3:latest`). Rate-limit errors are retried with growing waits; other errors are reported, never fed to the Judge.
- **Structured verdict:** the Judge fills a schema (BUY/SELL/HOLD, confidence, reasons, risks, cited figures,
  conclusion) and the memo is built from it, so the label and the text cannot disagree. A model that cannot do structured
  output falls back to a text memo.
- **Usage:** token counts for each debate are shown under the verdict. A cost estimate appears only if you set the
  per-million-token prices in the environment.
- **Closing the tab** stops the debate before its next model call (calls already running finish).
- **Live progress:** the backend streams each step to the browser with Server-Sent Events.
- **Safe rendering:** the browser shows model output as Markdown, never as raw HTML.

## Quant signals (volatility)

`src/tools/quant.py` forecasts how much a stock is likely to swing over the next 21 trading days and reports how
that method has done on the stock's own past months. It does **not** forecast direction. Design:
`docs/DESIGN_QUANT_AND_AGENT_TOOLS.md`; decisions: `decision.md`.

- **Method on a request:** the one-year average of squared daily returns (`QUANT_DEFAULT_MODEL=long_run`). It was
  chosen offline, not per stock, and takes about 16 ms. EWMA, naive, and the GARCH family are selectable.
- **What the agents see:** the forecast, the ±1σ monthly move, the volatility regime, recent returns and one sentence
  on the method's record for this stock. They never see per-model scores or the share of past months that rose.
- **What the browser gets:** the full block (`quant`, `schema_version` 1), including the track record.
- **If it fails** (short history, provider down, switched off with `QUANT_ENABLED=false`), the debate runs without it.

Offline evaluation (`python scripts/eval_quant.py`, results in `eval/results/`): 60 US stocks, 10 years of prices,
models chosen on 2018-2023 test dates and reported on 2024-2026 test dates they never saw.

- Every volatility model beat the naive guess "next month equals last month" (median error ratio 0.60 to 0.80).
- The shipped one-year average cut median forecast error 39% below the naive guess (p = 0.0024), and its stated ±1σ
  range held 67.1% of real monthly moves (68% expected); ±2σ held 93.8% (95% expected).
- Against a plain one-year average, the best model (GJR-GARCH) was about 3% better, not statistically significant,
  which is why the one-year average is the default.

Limits: only stocks that still trade, prices adjusted for later splits and dividends, about 34 independent
months in the held-out period. The `arch` and `scipy` packages are only needed for the evaluation and tests
(`requirements-dev.txt`).

## Run it

Requirements: Python 3.12+, Node 20+, and optionally [Ollama](https://ollama.com) (`ollama pull gemma3`).

```bash
# backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn src.api:app --port 8000

# frontend (another terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

Or with Docker (backend on 8000, frontend on 5173):

```bash
docker compose up --build
```
Inside Docker, Ollama on your computer is reached at `host.docker.internal:11434` (override with `OLLAMA_BASE_URL`).

### Using a Gemini key
Type your key in the page. It is sent to the backend in an `X-Api-Key` header (never in the URL or body), used for that
request only, redacted from logs and errors, and never returned. Leave it empty to use local Ollama.

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/debate` | `{"ticker": "NVDA"}`, optional `X-Api-Key` header. Returns the whole debate as JSON. |
| POST | `/api/debate/stream` | Same input; Server-Sent Events: `start`, one `stage` per finished step, then `done` or `error`. |
| GET | `/api/search?q=nvi` | Ticker suggestions (a built-in list of about 80 large companies). |
| GET | `/api/config` | Whether demo mode is on (a visitor may run a debate without a key, within daily caps). |
| GET | `/api/health` | Liveness. |

Errors use clear statuses: 404 unknown ticker, 401 key rejected, 429 rate limited (by us or the provider), 503 model or
data source unreachable, 502 model error, 422 invalid ticker.

## Configuration

Environment variables (see `.env.example`): `CORS_ORIGINS`, `RATE_LIMIT_PER_MINUTE`, `GEMINI_MODEL`, `OLLAMA_MODEL`,
`OLLAMA_BASE_URL`, `LLM_MAX_RETRIES`, `LLM_RETRY_BASE_DELAY`, `DATA_CACHE_TTL_SECONDS`, `TRUSTED_PROXY_HOPS` (set to the
number of reverse proxies in front of the app), `DEMO_API_KEY` and its caps (demo mode is off unless set),
`GEMINI_INPUT_USD_PER_M` / `GEMINI_OUTPUT_USD_PER_M` (optional cost estimate). The frontend reads `VITE_API_URL`.

## Tests

```bash
pytest -q                       # backend: 178 tests, no network or model needed
cd frontend && npm test         # frontend: 21 tests
ruff check .  &&  cd frontend && npm run lint
```
CI runs all of this on every push (`.github/workflows/ci.yml`).

## Security notes

- The key is header-only, redacted, and never echoed; the response is an explicit whitelist of fields.
- CORS is limited to configured origins with no credentials; the debate endpoints are rate limited per client address
  (in memory, so one counter per process; put a proxy or shared store in front for strict limits).
- Tickers are validated; model output is rendered as text/Markdown only (no HTML, no images, safe links).
- Containers run as non-root users; dependencies are pinned.

## Known limitations

- The Judge is another language model reading the same data. Nothing here measures whether verdicts are correct; they are
  not predictions to act on.
- News comes from scraping DuckDuckGo, which can fail or be blocked; the debate then runs on price and ratios only.
- The ticker search is a short fixed list; the debate itself accepts any symbol Yahoo Finance knows.
- Rate limiting and demo caps are per process (a restart resets them). Behind a proxy, set `TRUSTED_PROXY_HOPS`.
- Every test uses a fake model. `scripts/live_eval.py` measures consistency, position bias and how often cited numbers
  exist in the data on a real model; it needs your own Gemini key and **has not been run yet**, so there are no results
  to quote.

## License

MIT License.
