"""A tiny thread-safe time-based cache for market data and news."""
import functools
import threading
import time
from typing import Any, Callable


def ttl_cache(seconds: Callable[[], float] | float, now: Callable[[], float] = time.monotonic):
    """Cache a function's successful results per argument tuple for `seconds` (a number or a callable returning one).

    Results that are dicts with an "error" key, or empty lists, are not cached, so a temporary failure is retried."""

    def decorator(fn):
        store: dict[Any, tuple[float, Any]] = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args):
            ttl = seconds() if callable(seconds) else seconds
            key = args
            with lock:
                hit = store.get(key)
                if hit and now() - hit[0] < ttl:
                    return hit[1]
            value = fn(*args)
            failed = (isinstance(value, dict) and "error" in value) or value == []
            if not failed and ttl > 0:
                with lock:
                    store[key] = (now(), value)
                    if len(store) > 500:                      # keep memory bounded: drop expired entries
                        for k in [k for k, (t, _) in store.items() if now() - t >= ttl]:
                            store.pop(k, None)
            return value

        wrapper.cache_clear = lambda: store.clear()  # type: ignore[attr-defined]
        return wrapper

    return decorator
