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
- **Models:** Google Gemini (`gemini-2.0-flash`) when you enter an API key, otherwise a local Ollama model
  (`gemma3:latest`). Rate-limit errors are retried with growing waits; other errors are reported, never fed to the Judge.
- **Live progress:** the backend streams each step to the browser with Server-Sent Events.
- **Safe rendering:** the browser shows model output as Markdown, never as raw HTML.

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
| GET | `/api/health` | Liveness. |

Errors use clear statuses: 404 unknown ticker, 401 key rejected, 429 rate limited (by us or the provider), 503 model or
data source unreachable, 502 model error, 422 invalid ticker.

## Configuration

Environment variables (see `.env.example`): `CORS_ORIGINS`, `RATE_LIMIT_PER_MINUTE`, `GEMINI_MODEL`, `OLLAMA_MODEL`,
`OLLAMA_BASE_URL`, `LLM_MAX_RETRIES`, `LLM_RETRY_BASE_DELAY`, `DATA_CACHE_TTL_SECONDS`. The frontend reads `VITE_API_URL`.

## Tests

```bash
pytest -q                       # backend: 75 tests, no network or model needed
cd frontend && npm test         # frontend: 11 tests
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
- Rate limiting is per process and uses the connecting address, so behind a proxy it needs configuring.

## License

MIT License.
