from __future__ import annotations

import math
import time


class RedisRateLimiter:
    def __init__(self, redis_conn, max_capacity: int, refill_rate: float):
        if max_capacity <= 0:
            raise ValueError("max_capacity must be > 0")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be > 0")

        self.redis = redis_conn
        self.max_capacity = max_capacity
        self.refill_rate = refill_rate

        self._scale = 1000
        self._capacity_scaled = max_capacity * self._scale
        self._refill_per_sec_scaled = max(1, int(round(refill_rate * self._scale)))

        self._script = self.redis.register_script(
            """
            local key = KEYS[1]

            local capacity = tonumber(ARGV[1])
            local refill_per_sec = tonumber(ARGV[2])
            local now_ms = tonumber(ARGV[3])
            local cost = tonumber(ARGV[4])
            local scale = tonumber(ARGV[5])

            local bucket = redis.call("HMGET", key, "tokens", "last_ms")
            local tokens = tonumber(bucket[1])
            local last_ms = tonumber(bucket[2])

            if not tokens or not last_ms then
                tokens = capacity
                last_ms = now_ms
            end

            if now_ms < last_ms then
                now_ms = last_ms
            end

            local elapsed_ms = now_ms - last_ms
            if elapsed_ms > 0 then
                local refill = math.floor((elapsed_ms * refill_per_sec) / 1000)
                if refill > 0 then
                    tokens = math.min(capacity, tokens + refill)
                    last_ms = now_ms
                end
            end

            local allowed = 0
            local retry_after = 0

            if tokens >= cost then
                tokens = tokens - cost
                allowed = 1
            else
                local deficit = cost - tokens
                retry_after = math.ceil(deficit / refill_per_sec)
                if retry_after < 1 then
                    retry_after = 1
                end
            end

            redis.call("HSET", key, "tokens", tokens, "last_ms", last_ms)

            local ttl = math.ceil(capacity / refill_per_sec)
            if ttl < 1 then
                ttl = 1
            end
            redis.call("EXPIRE", key, ttl)

            local remaining = math.floor(tokens / scale)
            if remaining < 0 then
                remaining = 0
            end

            return {allowed, remaining, retry_after}
            """
        )

    def allow(self, client_id: str, cost: int = 1) -> dict[str, int | bool]:
        if cost <= 0:
            raise ValueError("cost must be > 0")

        key = f"circuit:rl:{client_id}"
        now_ms = int(time.time() * 1000)
        cost_scaled = cost * self._scale

        allowed, remaining, retry_after = self._script(
            keys=[key],
            args=[
                self._capacity_scaled,
                self._refill_per_sec_scaled,
                now_ms,
                cost_scaled,
                self._scale,
            ],
        )

        return {
            "allowed": bool(int(allowed)),
            "limit": self.max_capacity,
            "remaining": int(remaining),
            "retry_after": int(retry_after),
        }

    def headers(self, result: dict[str, int | bool]) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(result["limit"]),
            "X-RateLimit-Remaining": str(result["remaining"]),
        }

        if not result["allowed"] and result["retry_after"] > 0:
            headers["Retry-After"] = str(result["retry_after"])

        return headers