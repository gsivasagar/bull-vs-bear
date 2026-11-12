import asyncio
import json
import logging
import re
from typing import Annotated, Any, Dict

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from src import config
from src.cancel import Cancelled, new_event, run_config
from src.data.tickers import TICKERS
from src.demo import DemoCaps
from src.errors import DebateError
from src.graph import get_graph
from src.ratelimit import RateLimiter

log = logging.getLogger(__name__)

app = FastAPI(title="Investment Debate API")

# The browser app is on a different origin. No cookies are used, so credentials stay off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Api-Key"],
)

_limiter = RateLimiter(config.RATE_LIMIT_PER_MINUTE)
_demo = DemoCaps(config.DEMO_PER_VISITOR_PER_DAY, config.DEMO_GLOBAL_PER_DAY)
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
STAGES = ["fetch_data", "bull_agent", "bear_agent", "judge_agent"]


class DebateRequest(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def _valid_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not _TICKER.match(value):
            raise ValueError("Enter a stock symbol such as NVDA or BRK.B")
        return value


def get_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str | None:
    """The user's Gemini key, sent in a header (not the URL or body, so it stays out of logs and responses)."""
    key = (x_api_key or "").strip()
    if not key:
        return None
    if len(key) > 200 or re.search(r"\s", key):
        raise HTTPException(status_code=400, detail="That API key does not look valid.")
    return key


def client_ip(request: Request) -> str:
    """The visitor's address. Behind N trusted proxies it is the Nth entry from the right of X-Forwarded-For (anything
    further left can be forged). With no trusted proxy the header is ignored and the socket address is used."""
    hops = config.TRUSTED_PROXY_HOPS
    if hops > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    client = client_ip(request)
    if not _limiter.allow(client):
        raise HTTPException(status_code=429, detail="Too many requests. Try again in a minute.",
                            headers={"Retry-After": "60"})


@app.exception_handler(DebateError)
async def debate_error_handler(_: Request, exc: DebateError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.public_message})


def summarize_usage(calls: list) -> Dict[str, Any]:
    """Tokens (and a cost estimate when prices are configured) for the model calls made so far."""
    tin = sum(c.get("input_tokens", 0) for c in calls)
    tout = sum(c.get("output_tokens", 0) for c in calls)
    cost = None
    if config.GEMINI_INPUT_USD_PER_M and config.GEMINI_OUTPUT_USD_PER_M:
        try:
            rate_in, rate_out = float(config.GEMINI_INPUT_USD_PER_M), float(config.GEMINI_OUTPUT_USD_PER_M)
            cost = round((tin * rate_in + tout * rate_out) / 1e6, 6)
        except ValueError:
            cost = None
    return {"calls": len(calls), "input_tokens": tin, "output_tokens": tout, "cost_usd": cost}


def build_result(state: Dict[str, Any]) -> Dict[str, Any]:
    """The response sent to the browser: an explicit whitelist, so nothing else in the state (like the key) can leak."""
    price = state.get("price_data") or {}
    return {
        "ticker": state.get("ticker"),
        "price_data": {k: price.get(k) for k in ("company_name", "current_price", "currency", "sector")},
        "financials": state.get("financials") or {},
        "quant": state.get("quant") or {},
        "news": [{"title": n.get("title", ""), "source": n.get("source", ""), "url": n.get("url", "")}
                 for n in state.get("news_data") or []],
        "bull_argument": state.get("bull_argument", ""),
        "bear_argument": state.get("bear_argument", ""),
        "verdict": state.get("verdict", ""),
        "recommendation": state.get("recommendation", "UNKNOWN"),
        "judge": state.get("judge") or {},
        "usage": summarize_usage(state.get("usage") or []),
        "disclaimer": config.DISCLAIMER,
    }


def _initial_state(ticker: str, api_key: str | None, model: str | None = None) -> Dict[str, Any]:
    return {"ticker": ticker, "api_key": api_key, "model": model, "price_data": {}, "financials": {}, "quant": {},
            "news_data": [], "bull_argument": "", "bear_argument": "", "verdict": "", "recommendation": "",
            "judge": {}, "usage": []}


def resolve_key(request: Request, api_key: str | None) -> tuple[str | None, str | None, bool]:
    """(key to use, model override, whether a demo run was reserved). A visitor key always wins; the server's demo key
    is used only when none is sent, demo mode is on, and the visitor is within the daily caps."""
    if api_key or not config.DEMO_API_KEY:
        return api_key, None, False
    refusal = _demo.take(client_ip(request))
    if refusal:
        raise HTTPException(status_code=429, detail=refusal)
    return config.DEMO_API_KEY, config.DEMO_MODEL, True


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Investment Debate API is running"}


@app.get("/api/config")
def public_config():
    """What the page needs to know: whether it may run without a visitor key."""
    return {"demo_enabled": bool(config.DEMO_API_KEY), "demo_per_visitor_per_day": config.DEMO_PER_VISITOR_PER_DAY}


def _example_files() -> Dict[str, Any]:
    if not config.EXAMPLES_DIR.is_dir():
        return {}
    return {f.stem: f for f in sorted(config.EXAMPLES_DIR.glob("*.json")) if _TICKER.match(f.stem)}


@app.get("/api/examples")
def list_examples():
    """Saved real debates: no model call, no key. Each carries the date and model it was made with."""
    out = []
    for ticker, path in _example_files().items():
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        out.append({"ticker": ticker, "recommendation": data.get("recommendation"), "saved_on": data.get("saved_on")})
    return out


@app.get("/api/examples/{ticker}")
def get_example(ticker: str):
    path = _example_files().get(ticker.strip().upper())        # looked up in a fixed set: no user text reaches a path
    if path is None:
        raise HTTPException(status_code=404, detail="No saved example for that ticker.")
    return json.loads(path.read_text())


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search")
def search_tickers(q: Annotated[str, Query(max_length=40)] = ""):
    q = q.strip().lower()
    if not q:
        return []
    results = []
    for t in TICKERS:
        if q in t["symbol"].lower() or q in t["name"].lower():
            results.append(t)
            if len(results) >= 10:
                break
    return results


# `def` (not `async def`): the work is blocking, so FastAPI runs it in a worker thread and other requests keep flowing.
@app.post("/api/debate")
def run_debate(request: Request, body: DebateRequest, api_key: Annotated[str | None, Depends(get_api_key)],
               _: Annotated[None, Depends(check_rate_limit)]):
    key, model, reserved = resolve_key(request, api_key)
    try:
        final_state = get_graph().invoke(_initial_state(body.ticker, key, model))
    except DebateError as exc:
        if reserved and exc.status_code in (404, 503):   # failed before any model call: do not charge the visitor
            _demo.refund(client_ip(request))
        raise
    return build_result(final_state)


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


SSE_KEEPALIVE_SECONDS = 5.0


@app.post("/api/debate/stream")
async def stream_debate(request: Request, body: DebateRequest, api_key: Annotated[str | None, Depends(get_api_key)],
                        _: Annotated[None, Depends(check_rate_limit)]):
    """Server-Sent Events: a `start` event, one `stage` event as each step finishes, then `done` (or `error`).

    A comment line is sent every few seconds. If the visitor has closed the tab, that write fails, and the debate is
    told to stop before its next model call."""
    key, model, _reserved = resolve_key(request, api_key)
    cancel = new_event()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def produce() -> None:
        state: Dict[str, Any] = {}
        put = lambda item: loop.call_soon_threadsafe(queue.put_nowait, item)  # noqa: E731
        put(_sse("start", {"ticker": body.ticker, "stages": STAGES}))
        try:
            for update in get_graph().stream(_initial_state(body.ticker, key, model), config=run_config(cancel),
                                             stream_mode="updates"):
                for node, payload in update.items():
                    payload = payload or {}
                    usage = payload.get("usage")
                    state.update({k: v for k, v in payload.items() if k != "usage"})
                    state["usage"] = (state.get("usage") or []) + (usage or [])
                    put(_sse("stage", {"stage": node, "result": build_result({**state, "ticker": body.ticker})}))
            put(_sse("done", build_result({**state, "ticker": body.ticker})))
        except Cancelled:
            log.info("Debate for %s stopped: the visitor left", body.ticker)
        except DebateError as exc:
            put(_sse("error", {"status": exc.status_code, "detail": exc.public_message}))
        except Exception:
            log.exception("Debate stream failed")
            put(_sse("error", {"status": 500, "detail": "Something went wrong while running the debate."}))
        finally:
            put(None)

    async def events():
        loop.run_in_executor(None, produce)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), SSE_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if item is None:
                    break
                yield item
        finally:
            cancel.set()                      # runs when the client disconnects (or the stream ends normally)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
