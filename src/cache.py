"""A tiny thread-safe time-based cache for market data and news."""
import functools
import threading
import time
from typing import Any, Callable


def ttl_cache(seconds: Callable[[], float] | float, now: Callable[[], float] = time.monotonic,
              single_flight: bool = False):
    """Cache a function's successful results per argument tuple for `seconds` (a number or a callable returning one).

    Results that are dicts with an "error" key, or empty lists, are not cached, so a temporary failure is retried.
    With `single_flight`, callers that arrive while the same arguments are being computed wait for that one
    computation instead of repeating it (a failed result is not shared, so a waiter then tries for itself)."""

    def decorator(fn):
        store: dict[Any, tuple[float, Any]] = {}
        lock = threading.Lock()
        key_locks: dict[Any, threading.Lock] = {}

        def lookup(key, ttl):
            with lock:
                hit = store.get(key)
                if hit and now() - hit[0] < ttl:
                    return hit
            return None

        @functools.wraps(fn)
        def wrapper(*args):
            ttl = seconds() if callable(seconds) else seconds
            key = args
            hit = lookup(key, ttl)
            if hit:
                return hit[1]
            if single_flight:
                with lock:
                    flight = key_locks.setdefault(key, threading.Lock())
                with flight:
                    hit = lookup(key, ttl)                    # someone else may have finished while we waited
                    if hit:
                        return hit[1]
                    return compute(key, args, ttl)
            return compute(key, args, ttl)

        def compute(key, args, ttl):
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
