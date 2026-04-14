import time
import redis


LUA_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", key, "tokens", "last_ts")
local tokens = tonumber(data[1])
local last_ts = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_ts = now
end

local elapsed = math.max(0, now - last_ts)
tokens = math.min(capacity, tokens + (elapsed * refill_rate))

if tokens >= 1 then
    redis.call("HMSET", key, "tokens", tokens - 1, "last_ts", now)
    redis.call("EXPIRE", key, 86400)
    return 1
end

return 0
"""


class RedisRateLimiter:
    def __init__(
        self,
        redis_client: redis.Redis,
        capacity: int,
        refill_rate_per_sec: float,
        key_prefix: str = "circuit:rl",
    ):
        self.r = redis_client
        self.capacity = capacity
        self.refill_rate_per_sec = refill_rate_per_sec
        self.key_prefix = key_prefix
        
        self._script = self.r.register_script(LUA_SCRIPT)

    def allow(self, client_key: str) -> bool:
        key = f"{self.key_prefix}:{client_key}"
        
        allowed = self._script(
            keys=[key],
            args=[self.capacity, self.refill_rate_per_sec, time.time()],
        )

        return bool(allowed)