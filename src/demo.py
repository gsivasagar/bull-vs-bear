"""Demo mode: a visitor without their own key may use the server's key, within hard daily caps (per visitor and total).

In memory and per process, like the rate limiter: a restart resets the counts, so also set a spend limit on the key."""
import threading
from datetime import datetime, timezone
from typing import Callable


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class DemoCaps:
    def __init__(self, per_visitor: int, total: int, today: Callable[[], str] = _today):
        self.per_visitor, self.total, self._today = per_visitor, total, today
        self._day = today()
        self._visitors: dict[str, int] = {}
        self._used = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        day = self._today()
        if day != self._day:
            self._day, self._visitors, self._used = day, {}, 0

    def take(self, visitor: str) -> str | None:
        """Reserve one demo run. Returns None when allowed, otherwise the reason it was refused."""
        with self._lock:
            self._roll()
            if self._used >= self.total:
                return "The free demo has reached today's limit. Try again tomorrow, or enter your own Gemini API key."
            if self._visitors.get(visitor, 0) >= self.per_visitor:
                return (f"You have used your {self.per_visitor} free demo debates for today. "
                        "Try again tomorrow, or enter your own Gemini API key.")
            self._visitors[visitor] = self._visitors.get(visitor, 0) + 1
            self._used += 1
            return None

    def refund(self, visitor: str) -> None:
        """Give the run back when it failed before any model call was made."""
        with self._lock:
            if self._visitors.get(visitor, 0) > 0:
                self._visitors[visitor] -= 1
                self._used = max(0, self._used - 1)
