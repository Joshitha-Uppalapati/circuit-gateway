from __future__ import annotations

import time
from collections import OrderedDict


class TokenBucket:
    def __init__(self, capacity: int, refill_rate_per_sec: float):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.tokens = capacity
        self.last_refill = time.time()

    def allow(self) -> bool:
        now = time.time()
        elapsed = now - self.last_refill

        refill_amount = elapsed * self.refill_rate
        if refill_amount > 0:
            self.tokens = min(self.capacity, self.tokens + refill_amount)
            self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True

        return False


class RateLimiter:
    def __init__(
        self,
        capacity: int = 20,
        refill_rate_per_sec: float = 5,
        max_buckets: int = 1000,
    ):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.max_buckets = max_buckets
        self.buckets: OrderedDict[str, TokenBucket] = OrderedDict()

    def allow(self, client_key: str) -> bool:
        bucket = self.buckets.get(client_key)

        if bucket is None:
            if len(self.buckets) >= self.max_buckets:
                self.buckets.popitem(last=False)

            bucket = TokenBucket(self.capacity, self.refill_rate)
            self.buckets[client_key] = bucket
        else:
            self.buckets.move_to_end(client_key)

        return bucket.allow()