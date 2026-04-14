from __future__ import annotations

import time
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: int = 30):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self.state = BreakerState.CLOSED
        self.fail_count = 0
        self.opened_at: float | None = None
        self.half_open_in_flight = False

    def allow_request(self) -> bool:
        now = time.time()

        if self.state == BreakerState.CLOSED:
            return True

        if self.state == BreakerState.OPEN:
            if self.opened_at is not None and now - self.opened_at >= self.cooldown_seconds:
                self.state = BreakerState.HALF_OPEN
                self.half_open_in_flight = False
            else:
                return False

        if self.state == BreakerState.HALF_OPEN:
            if self.half_open_in_flight:
                return False

            self.half_open_in_flight = True
            return True

        return False

    def record_success(self) -> None:
        self.fail_count = 0
        self.state = BreakerState.CLOSED
        self.half_open_in_flight = False
        self.opened_at = None

    def record_failure(self) -> None:
        self.fail_count += 1

        if self.state == BreakerState.HALF_OPEN:
            self._trip()
            return

        if self.fail_count >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self.state = BreakerState.OPEN
        self.opened_at = time.time()
        self.half_open_in_flight = False