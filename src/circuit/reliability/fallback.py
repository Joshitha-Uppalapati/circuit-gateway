from typing import Callable, Awaitable, Dict, Any


async def with_fallback(
    primary_call: Callable[[], Awaitable[Dict[str, Any]]],
    fallback_call: Callable[[], Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    try:
        result = await primary_call()

        if isinstance(result, dict) and "error" in result:
            raise RuntimeError("primary_failed")

        return result

    except Exception:
        return await fallback_call()