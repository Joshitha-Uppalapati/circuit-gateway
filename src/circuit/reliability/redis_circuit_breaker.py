from __future__ import annotations

import logging
import time

from circuit.storage.redis_client import get_redis_client

logger = logging.getLogger("circuit.breaker")


class RedisCircuitBreaker:
    def __init__(self, name: str):
        self.redis = get_redis_client()
        self.name = name
        self.window_size = 5
        self.failure_rate_threshold = 0.6
        self.recovery_timeout = 10
        self.window_ttl = max(self.window_size * self.recovery_timeout, 30)

        if self.redis is None:
            self._allow_script = None
            self._success_script = None
            self._failure_script = None
            return

        self._allow_script = self.redis.register_script(
            """
            local state_key = KEYS[1]
            local opened_at_key = KEYS[2]
            local probe_key = KEYS[3]

            local now_ts = tonumber(ARGV[1])
            local recovery_timeout = tonumber(ARGV[2])

            local state = redis.call("GET", state_key)

            if not state then
                redis.call("SETEX", state_key, math.ceil(recovery_timeout), "closed")
                return {1, "closed", "closed"}
            end

            if state == "closed" then
                return {1, "closed", "closed"}
            end

            if state == "open" then
                local opened_at = tonumber(redis.call("GET", opened_at_key) or "0")

                if opened_at > 0 and (now_ts - opened_at) >= recovery_timeout then
                    redis.call("SETEX", state_key, math.ceil(recovery_timeout), "half_open")

                    if redis.call("SET", probe_key, "1", "NX", "EX", math.ceil(recovery_timeout)) then
                        return {1, "open", "half_open"}
                    end

                    return {0, "open", "half_open"}
                end

                return {0, "open", "open"}
            end

            if state == "half_open" then
                if redis.call("SET", probe_key, "1", "NX", "EX", math.ceil(recovery_timeout)) then
                    return {1, "half_open", "half_open"}
                end

                return {0, "half_open", "half_open"}
            end

            return {0, state, state}
            """
        )

        self._success_script = self.redis.register_script(
            """
            local state_key = KEYS[1]
            local failures_key = KEYS[2]
            local total_key = KEYS[3]
            local opened_at_key = KEYS[4]
            local probe_key = KEYS[5]

            local window_ttl = tonumber(ARGV[1])

            local state = redis.call("GET", state_key)

            if not state or state == "closed" then
                local total = redis.call("INCR", total_key)
                redis.call("EXPIRE", total_key, window_ttl)
                redis.call("SETEX", state_key, window_ttl, "closed")
                return {"closed", "closed", total}
            end

            if state == "half_open" then
                redis.call("SETEX", state_key, window_ttl, "closed")
                redis.call("DEL", failures_key)
                redis.call("DEL", total_key)
                redis.call("DEL", opened_at_key)
                redis.call("DEL", probe_key)
                return {"half_open", "closed", 0}
            end

            return {state, state, 0}
            """
        )

        self._failure_script = self.redis.register_script(
            """
            local state_key = KEYS[1]
            local failures_key = KEYS[2]
            local total_key = KEYS[3]
            local opened_at_key = KEYS[4]
            local probe_key = KEYS[5]

            local now_ts = tonumber(ARGV[1])
            local window_size = tonumber(ARGV[2])
            local failure_rate_threshold = tonumber(ARGV[3])
            local recovery_timeout = tonumber(ARGV[4])
            local window_ttl = tonumber(ARGV[5])

            local state = redis.call("GET", state_key)

            if state == "half_open" then
                redis.call("SETEX", state_key, math.ceil(recovery_timeout), "open")
                redis.call("SETEX", opened_at_key, math.ceil(recovery_timeout), tostring(now_ts))
                redis.call("DEL", failures_key)
                redis.call("DEL", total_key)
                redis.call("DEL", probe_key)
                return {"half_open", "open", 0, 0}
            end

            if not state then
                redis.call("SETEX", state_key, window_ttl, "closed")
                state = "closed"
            end

            if state == "open" then
                return {"open", "open", 0, 0}
            end

            local failures = redis.call("INCR", failures_key)
            local total = redis.call("INCR", total_key)

            redis.call("EXPIRE", failures_key, window_ttl)
            redis.call("EXPIRE", total_key, window_ttl)
            redis.call("EXPIRE", state_key, window_ttl)

            local rate = failures / total

            if total >= window_size and rate >= failure_rate_threshold then
                redis.call("SETEX", state_key, math.ceil(recovery_timeout), "open")
                redis.call("SETEX", opened_at_key, math.ceil(recovery_timeout), tostring(now_ts))
                redis.call("DEL", failures_key)
                redis.call("DEL", total_key)
                redis.call("DEL", probe_key)
                return {"closed", "open", failures, total}
            end

            if total >= window_size then
                redis.call("DEL", failures_key)
                redis.call("DEL", total_key)
            end

            return {"closed", "closed", failures, total}
            """
        )

    def _state_key(self) -> str:
        return f"circuit:breaker:{self.name}:state"

    def _fail_count_key(self) -> str:
        return f"circuit:breaker:{self.name}:failures"

    def _total_count_key(self) -> str:
        return f"circuit:breaker:{self.name}:total"

    def _opened_at_key(self) -> str:
        return f"circuit:breaker:{self.name}:opened_at"

    def _probe_key(self) -> str:
        return f"circuit:breaker:{self.name}:probe"

    def _decode(self, value):
        if isinstance(value, bytes):
            return value.decode()
        return value

    def _log_transition(self, previous_state: str, new_state: str):
        if previous_state != new_state:
            logger.warning(
                "breaker_transition name=%s from=%s to=%s",
                self.name,
                previous_state,
                new_state,
            )

    def _get_value(self, key: str):
        if self.redis is None:
            return None
        value = self.redis.get(key)
        return self._decode(value)

    def is_open(self) -> bool:
        state = self._get_value(self._state_key())
        return state == "open"

    def allow_request(self) -> bool:
        if self.redis is None:
            return True

        result = self._allow_script(
            keys=[
                self._state_key(),
                self._opened_at_key(),
                self._probe_key(),
            ],
            args=[time.time(), self.recovery_timeout],
        )

        allowed = bool(int(result[0]))
        previous_state = self._decode(result[1])
        new_state = self._decode(result[2])

        self._log_transition(previous_state, new_state)
        return allowed

    def record_success(self):
        if self.redis is None:
            return

        result = self._success_script(
            keys=[
                self._state_key(),
                self._fail_count_key(),
                self._total_count_key(),
                self._opened_at_key(),
                self._probe_key(),
            ],
            args=[self.window_ttl],
        )

        previous_state = self._decode(result[0])
        new_state = self._decode(result[1])

        self._log_transition(previous_state, new_state)

    def record_failure(self):
        if self.redis is None:
            return

        result = self._failure_script(
            keys=[
                self._state_key(),
                self._fail_count_key(),
                self._total_count_key(),
                self._opened_at_key(),
                self._probe_key(),
            ],
            args=[
                time.time(),
                self.window_size,
                self.failure_rate_threshold,
                self.recovery_timeout,
                self.window_ttl,
            ],
        )

        previous_state = self._decode(result[0])
        new_state = self._decode(result[1])

        self._log_transition(previous_state, new_state)