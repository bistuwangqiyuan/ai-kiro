"""Circuit breaker — 60s sliding window, 30% error threshold (design §10.6)."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    name: str
    window_s: float = 60.0
    threshold: float = 0.30
    min_samples: int = 10
    half_open_after_s: float = 30.0
    state: str = "closed"  # closed | open | half_open
    _events: deque = field(default_factory=deque)
    _opened_at: float = 0.0

    def _gc(self) -> None:
        now = time.time()
        while self._events and now - self._events[0][0] > self.window_s:
            self._events.popleft()

    def record(self, ok: bool) -> None:
        self._events.append((time.time(), ok))
        self._gc()
        if self.state == "closed":
            if len(self._events) >= self.min_samples:
                bad = sum(1 for _, k in self._events if not k)
                if bad / len(self._events) >= self.threshold:
                    self.state = "open"
                    self._opened_at = time.time()
        elif self.state == "half_open" and ok:
            self.state = "closed"
            self._events.clear()

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self._opened_at >= self.half_open_after_s:
                self.state = "half_open"
                return True
            return False
        return True
