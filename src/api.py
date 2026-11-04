import json
import logging
import re
from typing import Annotated, Any, Dict, Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from src import config
from src.data.tickers import TICKERS
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


def check_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not _limiter.allow(client):
        raise HTTPException(status_code=429, detail="Too many requests. Try again in a minute.",
                            headers={"Retry-After": "60"})


@app.exception_handler(DebateError)
async def debate_error_handler(_: Request, exc: DebateError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.public_message})


def build_result(state: Dict[str, Any]) -> Dict[str, Any]:
    """The response sent to the browser: an explicit whitelist, so nothing else in the state (like the key) can leak."""
    price = state.get("price_data") or {}
    return {
        "ticker": state.get("ticker"),
        "price_data": {k: price.get(k) for k in ("company_name", "current_price", "currency", "sector")},
        "financials": state.get("financials") or {},
        "news": [{"title": n.get("title", ""), "source": n.get("source", ""), "url": n.get("url", "")}
                 for n in state.get("news_data") or []],
        "bull_argument": state.get("bull_argument", ""),
        "bear_argument": state.get("bear_argument", ""),
        "verdict": state.get("verdict", ""),
        "recommendation": state.get("recommendation", "UNKNOWN"),
        "disclaimer": config.DISCLAIMER,
    }


def _initial_state(ticker: str, api_key: str | None) -> Dict[str, Any]:
    return {"ticker": ticker, "api_key": api_key, "price_data": {}, "financials": {}, "news_data": [],
            "bull_argument": "", "bear_argument": "", "verdict": "", "recommendation": ""}


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Investment Debate API is running"}


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
def run_debate(body: DebateRequest, api_key: Annotated[str | None, Depends(get_api_key)],
               _: Annotated[None, Depends(check_rate_limit)]):
    final_state = get_graph().invoke(_initial_state(body.ticker, api_key))
    return build_result(final_state)


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/api/debate/stream")
def stream_debate(body: DebateRequest, api_key: Annotated[str | None, Depends(get_api_key)],
                  _: Annotated[None, Depends(check_rate_limit)]):
    """Server-Sent Events: a `start` event, one `stage` event as each step finishes, then `done` (or `error`)."""

    def events() -> Iterator[str]:
        state: Dict[str, Any] = {}
        yield _sse("start", {"ticker": body.ticker, "stages": STAGES})
        try:
            for update in get_graph().stream(_initial_state(body.ticker, api_key), stream_mode="updates"):
                for node, payload in update.items():
                    state.update(payload or {})
                    yield _sse("stage", {"stage": node, "result": build_result({**state, "ticker": body.ticker})})
            yield _sse("done", build_result({**state, "ticker": body.ticker}))
        except DebateError as exc:
            yield _sse("error", {"status": exc.status_code, "detail": exc.public_message})
        except Exception:
            log.exception("Debate stream failed")
            yield _sse("error", {"status": 500, "detail": "Something went wrong while running the debate."})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
