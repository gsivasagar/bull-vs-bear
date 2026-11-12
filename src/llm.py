"""Choosing a model and calling it with bounded retries. API keys are never logged or put in error messages."""
import logging
import random
import re
import time
from typing import Any, Callable

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

from src import config
from src.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMUnavailableError

log = logging.getLogger(__name__)

_RATE_LIMIT_HINTS = ("429", "resource_exhausted", "quota", "rate limit", "rate-limit", "too many requests")
_CONNECTION_HINTS = ("failed to connect", "connection refused", "connect call failed", "connection error",
                     "all connection attempts failed", "network is unreachable", "no route to host",
                     "name or service not known", "nodename nor servname", "temporary failure in name resolution",
                     "timed out", "timeout")
_AUTH_HINTS = ("api key not valid", "api_key_invalid", "invalid api key", "api key expired", "permission_denied",
               "unauthenticated")
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")


def get_llm(api_key: str | None, temperature: float, model: str | None = None):
    """Gemini when the user supplied a key, otherwise a local Ollama model."""
    if api_key:
        return ChatGoogleGenerativeAI(model=model or config.GEMINI_MODEL, temperature=temperature,
                                      google_api_key=api_key)
    kwargs: dict[str, Any] = {"model": config.OLLAMA_MODEL, "temperature": temperature}
    if config.OLLAMA_BASE_URL:
        kwargs["base_url"] = config.OLLAMA_BASE_URL
    return ChatOllama(**kwargs)


def redact(text: str, api_key: str | None) -> str:
    """Remove the caller's key (and anything shaped like a Google key) from a message."""
    if api_key:
        text = text.replace(api_key, "***")
    return _GOOGLE_KEY.sub("***", text)


def _matches(exc: BaseException, hints: tuple[str, ...]) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(h in text for h in hints)


def is_rate_limit(exc: BaseException) -> bool:
    return _matches(exc, _RATE_LIMIT_HINTS)


def is_auth_problem(exc: BaseException) -> bool:
    return _matches(exc, _AUTH_HINTS)


def is_connection_problem(exc: BaseException) -> bool:
    # OSError covers every socket-level failure (refused, unreachable, no route, DNS); httpx wraps its own.
    return isinstance(exc, (OSError, httpx.TransportError)) or _matches(exc, _CONNECTION_HINTS)


def message_text(response: Any) -> str:
    """The text of a chat response (some models return a list of content parts)."""
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)


def usage_of(response: Any) -> dict:
    """Token counts from a chat response, when the provider reports them (zeros otherwise)."""
    meta = getattr(response, "usage_metadata", None) or {}
    return {"input_tokens": int(meta.get("input_tokens") or 0), "output_tokens": int(meta.get("output_tokens") or 0)}


def call_with_retry(call: Callable[[], Any], *, api_key: str | None = None, max_retries: int | None = None,
                    base_delay: float | None = None, sleep: Callable[[float], None] = time.sleep,
                    rand: Callable[[], float] = random.random) -> Any:
    """Run `call`; on a rate-limit error wait (1.5x longer each time, plus jitter) and try again.

    Raises LLMRateLimitError after the retries run out, LLMAuthError if the key is rejected, LLMUnavailableError if the
    model cannot be reached, and LLMError for anything else. Other errors are not retried."""
    retries = config.LLM_MAX_RETRIES if max_retries is None else max_retries
    delay = config.LLM_RETRY_BASE_DELAY if base_delay is None else base_delay
    attempt = 0
    while True:
        try:
            return call()
        except Exception as exc:
            safe = redact(str(exc), api_key)
            if is_rate_limit(exc):
                if attempt >= retries:
                    log.warning("Rate limited; giving up after %d retries", attempt)
                    raise LLMRateLimitError() from None
                wait = delay * (1 + 0.25 * rand())
                log.warning("Rate limited; retry %d/%d in %.1fs", attempt + 1, retries, wait)
                sleep(wait)
                delay *= 1.5
                attempt += 1
                continue
            if is_auth_problem(exc):
                log.warning("Model rejected the API key")
                raise LLMAuthError() from None
            if is_connection_problem(exc):
                log.warning("Model unreachable: %s", safe[:200])
                where = "the Gemini API" if api_key else "local Ollama (is it running, and is the model pulled?)"
                raise LLMUnavailableError(f"Could not reach {where}.") from None
            log.warning("Model error: %s", safe[:300])
            raise LLMError() from None


def invoke_with_retry(llm, messages, *, usage_sink: list | None = None, **retry) -> str:
    """Call the model and return its text. Token counts, when reported, are appended to `usage_sink`."""
    def call() -> str:
        response = llm.invoke(messages)
        if usage_sink is not None:
            usage_sink.append(usage_of(response))
        return message_text(response)

    return call_with_retry(call, **retry)


def invoke_structured(llm, messages, schema, *, usage_sink: list | None = None, **retry):
    """Ask for output that fits a pydantic `schema`. Returns the parsed object, or None when the model's answer did not
    fit the schema or the model cannot do structured output (the caller then falls back to plain text)."""
    def call():
        try:
            runnable = llm.with_structured_output(schema, include_raw=True)
        except (NotImplementedError, AttributeError):
            return None
        result = runnable.invoke(messages)
        if usage_sink is not None:
            usage_sink.append(usage_of(result.get("raw")))
        return None if result.get("parsing_error") else result.get("parsed")

    return call_with_retry(call, **retry)
