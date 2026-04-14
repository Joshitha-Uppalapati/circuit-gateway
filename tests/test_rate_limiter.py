import pytest

from circuit.reliability.redis_rate_limiter import RedisRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_capacity(fake_redis):
    limiter = RedisRateLimiter(fake_redis, max_capacity=2, refill_rate=0)

    result1 = limiter.allow("client1")
    result2 = limiter.allow("client1")
    result3 = limiter.allow("client1")

    assert result1["allowed"] is True
    assert result2["allowed"] is True
    assert result3["allowed"] is False
    assert result3["retry_after"] >= 1