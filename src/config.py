"""Settings, read once from environment variables (see .env.example)."""
import os
from pathlib import Path


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


CORS_ORIGINS = _csv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
# How many reverse proxies sit in front of the app (0 = none, use the socket address). With N, the client address is
# the Nth entry from the right of X-Forwarded-For: entries further left can be forged by the visitor.
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")

LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
LLM_RETRY_BASE_DELAY = float(os.getenv("LLM_RETRY_BASE_DELAY", "15"))

DATA_CACHE_TTL_SECONDS = float(os.getenv("DATA_CACHE_TTL_SECONDS", "300"))
# Daily closes change once a day (the unfinished day is dropped), so the quant path can cache them for an hour.
PRICE_HISTORY_TTL_SECONDS = float(os.getenv("PRICE_HISTORY_TTL_SECONDS", "3600"))

# Quantitative signals (design: docs/DESIGN_QUANT_AND_AGENT_TOOLS.md). The default model comes from the offline
# evaluation (eval/results): the one-year average, which needs no model fit.
QUANT_ENABLED = os.getenv("QUANT_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
QUANT_DEFAULT_MODEL = os.getenv("QUANT_DEFAULT_MODEL", "long_run").strip()
QUANT_FORECAST_TTL_SECONDS = float(os.getenv("QUANT_FORECAST_TTL_SECONDS", "3600"))

# Optional price per million tokens (USD) so the page can show a cost estimate. Left unset, only tokens are shown.
GEMINI_INPUT_USD_PER_M = os.getenv("GEMINI_INPUT_USD_PER_M", "").strip()
GEMINI_OUTPUT_USD_PER_M = os.getenv("GEMINI_OUTPUT_USD_PER_M", "").strip()

# Demo mode: visitors without a key use the server's key within hard daily caps. Off unless DEMO_API_KEY is set.
DEMO_API_KEY = os.getenv("DEMO_API_KEY", "").strip()
DEMO_MODEL = os.getenv("DEMO_MODEL", "").strip() or GEMINI_MODEL
DEMO_PER_VISITOR_PER_DAY = int(os.getenv("DEMO_PER_VISITOR_PER_DAY", "3"))
DEMO_GLOBAL_PER_DAY = int(os.getenv("DEMO_GLOBAL_PER_DAY", "50"))

# Saved real debates the page can show without calling a model (made by scripts/live_eval.py --examples).
EXAMPLES_DIR = Path(os.getenv("EXAMPLES_DIR", str(Path(__file__).resolve().parent.parent / "demo" / "examples")))

DISCLAIMER = (
    "For education and entertainment only. This is AI-generated text built from public data, "
    "not financial advice. It can be wrong or out of date; do your own research."
)
