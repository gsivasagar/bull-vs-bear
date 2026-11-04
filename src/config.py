"""Settings, read once from environment variables (see .env.example)."""
import os


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


CORS_ORIGINS = _csv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")

LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
LLM_RETRY_BASE_DELAY = float(os.getenv("LLM_RETRY_BASE_DELAY", "15"))

DATA_CACHE_TTL_SECONDS = float(os.getenv("DATA_CACHE_TTL_SECONDS", "300"))

DISCLAIMER = (
    "For education and entertainment only. This is AI-generated text built from public data, "
    "not financial advice. It can be wrong or out of date; do your own research."
)
