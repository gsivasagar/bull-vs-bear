"""Fixed-window per-client rate limiter (in memory: one process, best effort)."""
import threading
import time
from typing import Callable


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, now: Callable[[], float] = time.monotonic):
        self.limit, self.window, self._now = limit, window_seconds, now
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        t = self._now()
        with self._lock:
            start, count = self._windows.get(key, (t, 0))
            if t - start >= self.window:
                start, count = t, 0
            if count >= self.limit:
                self._windows[key] = (start, count)
                return False
            self._windows[key] = (start, count + 1)
            if len(self._windows) > 5000:
                self._windows = {k: v for k, v in self._windows.items() if t - v[0] < self.window}
            return True
