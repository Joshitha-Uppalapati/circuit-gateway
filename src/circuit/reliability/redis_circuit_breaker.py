import time
from circuit.storage.redis_client import get_redis_client


class RedisCircuitBreaker:
    def __init__(self, name: str):
        self.redis = get_redis_client()
        self.name = name

        # tuning knobs
        self.window_size = 5
        self.failure_rate_threshold = 0.6
        self.recovery_timeout = 10  # seconds

    def _state_key(self):
        return f"circuit:breaker:{self.name}:state"

    def _fail_count_key(self):
        return f"circuit:breaker:{self.name}:failures"

    def _total_count_key(self):
        return f"circuit:breaker:{self.name}:total"

    def _opened_at_key(self):
        return f"circuit:breaker:{self.name}:opened_at"

    def _get_value(self, key):
        val = self.redis.get(key)
        if val is None:
            return None
        if isinstance(val, bytes):
            return val.decode()
        return val

    def is_open(self):
        state = self._get_value(self._state_key())

        if state == "open":
            opened_at = self._get_value(self._opened_at_key())

            if opened_at:
                elapsed = time.time() - float(opened_at)

                # move to half-open after cooldown
                if elapsed > self.recovery_timeout:
                    self.redis.set(self._state_key(), "half_open")
                    return False

            return True

        return False

    def allow_request(self) -> bool:
        return not self.is_open()

    def record_success(self):
        state = self._get_value(self._state_key())
        self.redis.incr(self._total_count_key())
        
        if state == "half_open":
            self.redis.set(self._state_key(), "closed")
            self.redis.set(self._fail_count_key(), 0)
            self.redis.set(self._total_count_key(), 0)

    def record_failure(self):
        failures = self.redis.incr(self._fail_count_key())
        total = self.redis.incr(self._total_count_key())
        
        rate = failures / max(total, 1)
        print("breaker stats:", failures, total, rate)

        if total >= self.window_size:
            if rate >= self.failure_rate_threshold:
                self.redis.set(self._state_key(), "open")
                self.redis.set(self._opened_at_key(), time.time())

            # reset window AFTER evaluation
            self.redis.set(self._fail_count_key(), 0)
            self.redis.set(self._total_count_key(), 0)