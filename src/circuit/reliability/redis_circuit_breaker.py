import time
from circuit.storage.redis_client import get_redis_client

class RedisCircuitBreaker:
    def __init__(self, name: str):
        self.redis = get_redis_client()
        self.name = name

        self.failure_threshold = 3
        self.recovery_timeout = 10  # seconds

    def _state_key(self):
        return f"circuit:breaker:{self.name}:state"

    def _fail_count_key(self):
        return f"circuit:breaker:{self.name}:failures"

    def _opened_at_key(self):
        return f"circuit:breaker:{self.name}:opened_at"

    def is_open(self):
        state = self.redis.get(self._state_key())

        if state == "open":
            opened_at = self.redis.get(self._opened_at_key())

            if opened_at:
                elapsed = time.time() - float(opened_at)

                # allow half-open after timeout
                if elapsed > self.recovery_timeout:
                    self.redis.set(self._state_key(), "half_open")
                    return False

            return True

        return False

    def record_success(self):
        state = self.redis.get(self._state_key())
        # only close if we are in half-open
        if state == "half_open":
            self.redis.set(self._state_key(), "closed")
            self.redis.set(self._fail_count_key(), 0)

    def record_failure(self):
        failures = self.redis.incr(self._fail_count_key())

        if failures >= self.failure_threshold:
            self.redis.set(self._state_key(), "open")
            self.redis.set(self._opened_at_key(), time.time())