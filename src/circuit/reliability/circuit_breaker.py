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
        self.opened_at = None
        self.half_open_in_flight = False

    def allow_request(self) -> bool:
        if self.state == BreakerState.CLOSED:
            return True

        if self.state == BreakerState.OPEN:
            if time.time() - self.opened_at >= self.cooldown_seconds:
                self.state = BreakerState.HALF_OPEN
                self.half_open_in_flight = False
                return True
            return False

        if self.state == BreakerState.HALF_OPEN:
            if not self.half_open_in_flight:
                self.half_open_in_flight = True
                return True
            return False

        return False

    def record_success(self):
        self.fail_count = 0
        self.state = BreakerState.CLOSED
        self.half_open_in_flight = False
        self.opened_at = None

    def record_failure(self):
        self.fail_count += 1

        if self.state == BreakerState.HALF_OPEN:
            self._trip()
            return

        if self.fail_count >= self.failure_threshold:
            self._trip()

    def _trip(self):
        self.state = BreakerState.OPEN
        self.opened_at = time.time()
        self.half_open_in_flight = False