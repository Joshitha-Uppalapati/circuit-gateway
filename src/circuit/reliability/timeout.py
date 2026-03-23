import asyncio
from typing import Callable, Awaitable, Any


async def with_timeout(
    fn: Callable[[], Awaitable[Any]],
    timeout_seconds: float = 2.0,
):
    try:
        return await asyncio.wait_for(fn(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise RuntimeError("timeout")