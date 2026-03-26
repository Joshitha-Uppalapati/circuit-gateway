import time
import math

class RedisRateLimiter:
    def __init__(self, redis_conn, max_capacity: int, refill_rate: float):
        self.redis = redis_conn
        self.maxTokens = max_capacity
        self.refill_rate = refill_rate

        self.script_content = """
            local key = KEYS[1]
            local cap = tonumber(ARGV[1])
            local rate = tonumber(ARGV[2])
            local current_time = tonumber(ARGV[3])
            local req_cost = tonumber(ARGV[4])

            -- grab both fields at once
            local bucket = redis.call("HMGET", key, "tokens", "last_update")
            local current_tokens = tonumber(bucket[1])
            local last_update = tonumber(bucket[2])

            -- init bucket if this is a new client
            if current_tokens == nil then
                current_tokens = cap
                last_update = current_time
            end

            local elapsed = math.max(0, current_time - last_update)
            
            -- use floor to avoid weird fractional tokens like 0.16489... causing precision drift
            local refill_amount = math.floor(elapsed * rate)
            local new_tokens = math.min(cap, current_tokens + refill_amount)

            local is_allowed = 0

            -- check if we can afford the request
            if new_tokens >= req_cost then
                new_tokens = new_tokens - req_cost
                is_allowed = 1
            end
            
            -- always update the state so time moves forward for the client
            redis.call("HMSET", key, "tokens", new_tokens, "last_update", current_time)

            -- fix the TTL so it's not a hardcoded 60s. it should live exactly as long as it takes to refill
            local expire_time = math.ceil(cap / rate)
            redis.call("EXPIRE", key, expire_time)

            return {is_allowed, new_tokens}
        """
        
        self._lua = self.redis.register_script(self.script_content)

    def allow(self, client_id: str, cost: int = 1) -> tuple[bool, int]:
        # added proper namespace so we don't clash with the circuit breaker keys later
        cache_key = f"circuit:rl:{client_id}"
        now_ts = time.time()
        
        # print(f"DEBUG: checking rate limit for {client_id} at {now_ts}")
        
        try:
            res = self._lua(
                keys=[cache_key], 
                args=[self.maxTokens, self.refill_rate, now_ts, cost]
            )
            
            allowed_flag = res[0]
            tokens_left = res[1]
            
            return (allowed_flag == 1, tokens_left)
            
        except Exception as e:
            print("Redis lua script failed:", e)
            return True, 0