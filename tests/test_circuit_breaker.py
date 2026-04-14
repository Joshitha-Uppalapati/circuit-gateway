from __future__ import annotations


from circuit.reliability.circuit_breaker import CircuitBreaker, BreakerState


def test_trips_after_threshold():
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == BreakerState.CLOSED

    breaker.record_failure()
    assert breaker.state == BreakerState.OPEN


def test_half_open_allows_one_probe():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0)

    breaker.record_failure()
    assert breaker.state == BreakerState.OPEN

    assert breaker.allow_request() is True
    assert breaker.state == BreakerState.HALF_OPEN

    assert breaker.allow_request() is False


def test_recovers_on_success():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0)

    breaker.record_failure()
    assert breaker.state == BreakerState.OPEN

    breaker.allow_request()
    assert breaker.state == BreakerState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == BreakerState.CLOSED