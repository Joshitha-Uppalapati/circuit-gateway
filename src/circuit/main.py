from __future__ import annotations

import time
import uuid
import asyncio

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from circuit.middleware.auth import AuthMiddleware
from circuit.storage.redis_client import get_redis_client
from circuit.reliability.redis_rate_limiter import RedisRateLimiter
from circuit.reliability.redis_circuit_breaker import RedisCircuitBreaker
from circuit.reliability.retry import with_retries, DEFAULT_RETRY
from circuit.reliability.timeout import with_timeout

from circuit.providers.mock_openai import MockOpenAIProvider
from circuit.providers.ollama_provider import OllamaProvider

from circuit.observability.request_logger import log_request
from circuit.cost.calculator import calculate_cost
from circuit.quota import check_daily_quota

from circuit.config import settings

app = FastAPI()
app.add_middleware(AuthMiddleware)

# Global request timeout for the whole pipeline
GLOBAL_TIMEOUT_SECONDS = 3.0

print("RAW ENV:", os.getenv("CIRCUIT_API_KEYS"))
print("PARSED:", settings.api_keys)
 
# Debug: check what keys are actually loaded
print("Loaded API keys:", settings.api_keys)

# Redis setup
redis_client = get_redis_client()

if redis_client:
    print("redis connected")
else:
    print("redis not available")


# Rate limiter per client
rate_limiter = (
    RedisRateLimiter(redis_conn=redis_client, max_capacity=20, refill_rate=5.0)
    if redis_client
    else None
)


def breaker_state_value(breaker):
    """
    Safely read breaker state from Redis.
    Redis may return bytes or string depending on configuration.
    """
    if not breaker:
        return "disabled"

    state = breaker.redis.get(breaker._state_key())

    if state is None:
        return "closed"

    if isinstance(state, bytes):
        return state.decode()

    return str(state)


# Providers
try:
    primary_provider = MockOpenAIProvider()
except Exception as e:
    print("PRIMARY INIT FAILED:", e)
    primary_provider = None

fallback_provider = OllamaProvider()


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _handle_chat(request: Request):
    start = time.time()
    request_id = str(uuid.uuid4())

    client_key_hash = request.state.client_key_hash

    # Create a per-client circuit breaker
    breaker = (
        RedisCircuitBreaker(f"primary:{client_key_hash}")
        if redis_client
        else None
    )

    # Parse request body
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_json",
                    "message": "Malformed JSON request",
                }
            },
        )

    # Defaults
    result = None
    failure_reason = None
    provider_used = "primary"
    tokens_left = -1

    prompt_tokens = 0
    completion_tokens = 0

    # Track total requests for rate based breaker logic
    if breaker:
        breaker.redis.incr(f"{breaker.name}:total")
        breaker.redis.expire(f"{breaker.name}:total", 10)

    # Rate limiting
    if rate_limiter:
        allowed, tokens_left = rate_limiter.allow(client_key_hash)

        if not allowed:
            failure_reason = "rate_limited"

            try:
                log_request({
                    "request_id": request_id,
                    "client": client_key_hash,
                    "provider": "none",
                    "latency_ms": (time.time() - start) * 1000,
                    "breaker_state": breaker_state_value(breaker),
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "failure_reason": failure_reason,
                    "input_size": len(str(payload)),
                    "used_fallback": False,
                })
            except Exception:
                pass

            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                    }
                },
            )

    # Quota check
    ok, _, limit = check_daily_quota(client_key_hash, 0.0)

    if not ok:
        failure_reason = "quota_exceeded"

        try:
            log_request({
                "request_id": request_id,
                "client": client_key_hash,
                "provider": "none",
                "latency_ms": (time.time() - start) * 1000,
                "breaker_state": breaker_state_value(breaker),
                "tokens_in": 0,
                "tokens_out": 0,
                "failure_reason": failure_reason,
                "input_size": len(str(payload)),
                "used_fallback": False,
            })
        except Exception:
            pass

        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "quota_exceeded",
                    "message": f"Daily limit ${limit} reached",
                }
            },
        )

    # Primary provider attempt
    if primary_provider:
        try_primary = True

        if breaker and not breaker.allow_request():
            try_primary = False
            failure_reason = "breaker_open"

        if try_primary:
            try:
                result = await with_retries(
                    lambda: with_timeout(
                        lambda: primary_provider.chat_completions(payload),
                        timeout_seconds=1.2,
                    ),
                    config=DEFAULT_RETRY,
                )

                if not result or "choices" not in result:
                    raise RuntimeError("invalid response")

                if breaker:
                    breaker.record_success()

            except Exception as e:
                err = str(e).lower()

                failure_reason = "timeout" if "timeout" in err else "provider_error"

                if breaker:
                    breaker.record_failure()

                result = None

    # Fallback provider
    if result is None:
        provider_used = "fallback"

        try:
            result = await asyncio.wait_for(
                fallback_provider.chat_completions(payload),
                timeout=2.5,
            )

            # If fallback succeeds and no failure reason was set,
            # it means primary was skipped or unavailable
            if failure_reason is None:
                failure_reason = "primary_unavailable"

            # If breaker blocked primary, reflect that explicitly
            elif failure_reason == "provider_error" and breaker and not breaker.allow_request():
                failure_reason = "breaker_open"

        except asyncio.TimeoutError:
            failure_reason = "fallback_timeout"

            result = {
                "id": "timeout",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "none",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Request timed out.",
                        },
                        "finish_reason": "timeout",
                    }
                ],
                "usage": {},
            }

        except Exception:
            failure_reason = "fallback_error"

            result = {
                "id": "error",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "none",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Fallback failed.",
                        },
                        "finish_reason": "error",
                    }
                ],
                "usage": {},
            }

    # Extract usage
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    latency_ms = (time.time() - start) * 1000

    # Cost calculation
    if provider_used == "fallback":
        cost = 0.0
    else:
        cost = calculate_cost(
            result.get("model", "unknown"),
            prompt_tokens,
            completion_tokens,
        ) or 0.0

    result["latency_ms"] = latency_ms

    result["circuit"] = {
        "request_id": request_id,
        "client_key_hash": client_key_hash,
        "cost_usd": cost,
        "breaker_state": breaker_state_value(breaker),
        "provider": provider_used,
        "tokens_left": tokens_left,
    }

    result["meta"] = {
        "failure_reason": failure_reason,
        "used_fallback": provider_used == "fallback",
        "is_degraded": failure_reason is not None,
    }

    # Logging should never break the request
    try:
        log_request({
            "request_id": request_id,
            "client": client_key_hash,
            "provider": provider_used,
            "latency_ms": latency_ms,
            "breaker_state": breaker_state_value(breaker),
            "tokens_in": prompt_tokens,
            "tokens_out": completion_tokens,
            "failure_reason": failure_reason,
            "input_size": len(str(payload)),
            "used_fallback": provider_used == "fallback",
        })
    except Exception as e:
        print("LOGGING FAILED:", e)

    return result


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        return await asyncio.wait_for(
            _handle_chat(request),
            timeout=GLOBAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {
            "id": "global-timeout",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "none",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Global timeout.",
                    },
                    "finish_reason": "timeout",
                }
            ],
            "usage": {},
        }