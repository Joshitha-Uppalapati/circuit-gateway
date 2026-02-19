import time
from typing import Dict


class TokenBucket:
    def __init__(self, capacity: int, refill_rate_per_sec: float):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.tokens = capacity
        self.last_refill = time.time()

    def allow(self) -> bool:
        now = time.time()
        elapsed = now - self.last_refill

        # Refill tokens based on elapsed time
        refill_amount = elapsed * self.refill_rate
        if refill_amount > 0:
            self.tokens = min(self.capacity, self.tokens + refill_amount)
            self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True

        return False


class RateLimiter:
    def __init__(self, capacity: int = 20, refill_rate_per_sec: float = 5):
        """
        capacity: max burst size
        refill_rate_per_sec: tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.buckets: Dict[str, TokenBucket] = {}

    def allow(self, client_key: str) -> bool:
        if client_key not in self.buckets:
            self.buckets[client_key] = TokenBucket(
                self.capacity, self.refill_rate
            )

        return self.buckets[client_key].allow()