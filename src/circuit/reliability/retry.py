import asyncio
from dataclasses import dataclass


# simple retry config
@dataclass
class RetryConfig:
    max_attempts: int = 2
    delay_seconds: float = 0.2


# default config used across app
DEFAULT_RETRY = RetryConfig()


def is_retryable_error(error: Exception) -> bool:
    err = str(error).lower()

    if "timeout" in err:
        return True

    return False


async def with_retries(fn, config: RetryConfig = DEFAULT_RETRY):
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            return await fn()

        except Exception as e:
            last_exception = e

            # fail fast if not retryable
            if not is_retryable_error(e):
                raise e

            # last attempt → stop
            if attempt == config.max_attempts - 1:
                raise e

            # small delay before retry
            await asyncio.sleep(config.delay_seconds)

    # fallback safety
    raise last_exception