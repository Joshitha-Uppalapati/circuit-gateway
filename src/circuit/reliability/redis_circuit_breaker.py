import time
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BreakerConfig:
    def __init__(self, failure_threshold: int, window_seconds: int, cooldown_seconds: int):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds


class RedisCircuitBreaker:
    def __init__(self, redis_client, name: str, config: BreakerConfig):
        self.redis = redis_client
        self.name = name
        self.config = config

    def _key(self):
        return f"circuit:breaker:{self.name}"

    def _get_state(self):
        data = self.redis.hgetall(self._key())

        if not data:
            return {
                "state": BreakerState.CLOSED.value,
                "failure_count": 0,
                "last_failure_time": 0,
            }

        return {
            "state": data.get("state", BreakerState.CLOSED.value),
            "failure_count": int(data.get("failure_count", 0)),
            "last_failure_time": float(data.get("last_failure_time", 0)),
        }

    def _set_state(self, state, failure_count, last_failure_time):
        self.redis.hset(
            self._key(),
            mapping={
                "state": state,
                "failure_count": failure_count,
                "last_failure_time": last_failure_time,
            },
        )

    def allow_request(self) -> bool:
        data = self._get_state()
        state = data["state"]
        last_failure_time = data["last_failure_time"]

        now = time.time()

        if state == BreakerState.OPEN.value:
            if now - last_failure_time > self.config.cooldown_seconds:
                # move to half-open
                self._set_state(BreakerState.HALF_OPEN.value, 0, last_failure_time)
                return True
            return False

        return True

    def record_success(self):
        # reset breaker
        self._set_state(BreakerState.CLOSED.value, 0, 0)

    def record_failure(self):
        data = self._get_state()

        failure_count = data["failure_count"] + 1
        now = time.time()

        if failure_count >= self.config.failure_threshold:
            # open breaker
            self._set_state(BreakerState.OPEN.value, failure_count, now)
        else:
            self._set_state(data["state"], failure_count, now)

    @property
    def state(self):
        return self._get_state()["state"]