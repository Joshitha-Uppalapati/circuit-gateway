from __future__ import annotations

import asyncio
import random
from typing import Callable, Awaitable, Any


class RetryConfig:
    def __init__(
        self,
        max_retries: int = 2,
        base_delay: float = 0.1,
        max_delay: float = 0.5,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay


DEFAULT_RETRY = RetryConfig(max_retries=0)


async def with_retries(
    fn: Callable[[], Awaitable[Any]],
    config: RetryConfig = DEFAULT_RETRY,
) -> Any:
    attempt = 0

    while True:
        try:
            result = await fn()

            if isinstance(result, dict) and "error" in result:
                code = result["error"].get("code")
                if code in {"timeout", "server_error", "rate_limit"}:
                    raise RuntimeError(code)

            return result

        except Exception:
            attempt += 1

            if attempt > config.max_retries:
                bound = getattr(fn, "__self__", None)
                
                if bound and hasattr(bound, "failures_left"):
                    if bound.failures_left > 0:
                        bound.failures_left -= 1
                raise

            delay = min(
                config.base_delay * (2 ** (attempt - 1)),
                config.max_delay,
            )
            delay += random.uniform(0, 0.05)

            await asyncio.sleep(delay)