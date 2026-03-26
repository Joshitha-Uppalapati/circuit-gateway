from __future__ import annotations

import time
import uuid
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from circuit.middleware.auth import AuthMiddleware
from circuit.storage.redis_client import get_redis_client
from circuit.reliability.redis_rate_limiter import RedisRateLimiter
from circuit.reliability.redis_circuit_breaker import (
    RedisCircuitBreaker,
    BreakerConfig,
)
from circuit.reliability.retry import with_retries, DEFAULT_RETRY
from circuit.reliability.timeout import with_timeout

from circuit.providers.mock_openai import MockOpenAIProvider
from circuit.providers.ollama_provider import OllamaProvider

from circuit.observability.metrics import metrics
from circuit.observability.request_logger import log_request

from circuit.cost.calculator import calculate_cost
from circuit.quota import check_daily_quota


app = FastAPI()
app.add_middleware(AuthMiddleware)


# CONFIG
GLOBAL_TIMEOUT_SECONDS = 3.0


# PROVIDERS
try:
    primary_provider = MockOpenAIProvider()
except Exception as e:
    print("PRIMARY INIT FAILED:", e)
    primary_provider = None

fallback_provider = OllamaProvider()


# REDIS
redis_client = get_redis_client()

if redis_client:
    print("redis connected")
else:
    print("redis not available, using local state")


# RATE LIMITER
rate_limiter = (
    RedisRateLimiter(redis_conn=redis_client, max_capacity=20, refill_rate=5.0)
    if redis_client
    else None
)


# -------------------------
# CIRCUIT BREAKER
# -------------------------
breaker = (
    RedisCircuitBreaker(
        redis_client=redis_client,
        name="primary",
        config=BreakerConfig(
            failure_threshold=3,
            window_seconds=30,
            cooldown_seconds=20,
        ),
    )
    if redis_client
    else None
)


def breaker_state_value() -> str:
    if not breaker:
        return "disabled"
    state = breaker.state
    return state.value if hasattr(state, "value") else str(state)


# ROUTES
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def get_metrics():
    return metrics.snapshot()


@app.get("/metrics/prometheus")
async def get_prometheus():
    return metrics.prometheus()


# INTERNAL HANDLER
async def _handle_chat(request: Request):
    start = time.time()
    request_id = str(uuid.uuid4())

    client_key_hash = request.state.client_key_hash
    payload = await request.json()

    failure_reason = None
    provider_used = "primary"
    tokens_left = -1

    # rate limit
    if rate_limiter:
        is_allowed, tokens_left = rate_limiter.allow(client_key_hash)

        if not is_allowed:
            metrics.inc("rate_limit_blocked", client=client_key_hash)

            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                    }
                },
                headers={"X-RateLimit-Remaining": str(tokens_left)},
            )

        metrics.inc("rate_limit_allowed", client=client_key_hash)

    # quota
    ok, spent, limit = check_daily_quota(client_key_hash, 0.0)
    if not ok:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "quota_exceeded",
                    "message": f"Daily limit of ${limit} reached",
                }
            },
        )

    metrics.inc("total_requests", client=client_key_hash)

    result = None
    try_primary = primary_provider is not None

    # breaker state metric
    if breaker:
        metrics.inc(f"breaker_state_{breaker_state_value()}")

    # check breaker
    if try_primary and breaker and not breaker.allow_request():
        print("CIRCUIT OPEN: skipping primary")
        failure_reason = "breaker_open"
        try_primary = False

    # primary
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
                raise RuntimeError("invalid response from primary")

            if breaker:
                breaker.record_success()

        except Exception as e:
            err = str(e).lower()

            if "invalid response" in err:
                failure_reason = "invalid_response"
            elif "timeout" in err:
                failure_reason = "timeout"
            elif "forced failure" in err:
                failure_reason = "forced_failure"
            else:
                failure_reason = "provider_error"

            metrics.inc("total_failures", client=client_key_hash)
            metrics.inc(f"failure_{failure_reason}", client=client_key_hash)

            print(f"BREAKER STATE: {breaker_state_value()}")

            if breaker:
                breaker.record_failure()

            result = None

    # fallback
    if result is None:
        provider_used = "fallback"
        metrics.inc("fallback_requests", client=client_key_hash)

        task = asyncio.create_task(fallback_provider.chat_completions(payload))

        try:
            result = await asyncio.wait_for(task, timeout=2.5)

        except asyncio.TimeoutError:
            task.cancel()
            metrics.inc("fallback_timeouts", client=client_key_hash)

            return {
                "id": "timeout",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "none",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Request timed out. Please try again.",
                        },
                        "finish_reason": "timeout",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "latency_ms": int((time.time() - start) * 1000),
                "circuit": {
                    "request_id": request_id,
                    "client_key_hash": client_key_hash,
                    "cost_usd": 0.0,
                    "breaker_state": breaker_state_value(),
                    "provider": "timeout",
                    "tokens_left": tokens_left,
                },
            }

    # success
    latency_ms = (time.time() - start) * 1000

    metrics.observe_latency(latency_ms, client=client_key_hash)
    metrics.inc("total_success", client=client_key_hash)

    usage = result.get("usage", {})
    model = result.get("model", "unknown")

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    cost = calculate_cost(model, prompt_tokens, completion_tokens) or 0.0

    metrics.inc("total_tokens_input", prompt_tokens or 0)
    metrics.inc("total_tokens_output", completion_tokens or 0)

    result["latency_ms"] = latency_ms
    result["circuit"] = {
        "request_id": request_id,
        "client_key_hash": client_key_hash,
        "cost_usd": cost,
        "breaker_state": breaker_state_value(),
        "provider": provider_used,
        "tokens_left": tokens_left,
    }

    result["meta"] = {
        "failure_reason": failure_reason,
        "used_fallback": provider_used == "fallback",
        "is_degraded": provider_used == "fallback",
    }

    log_request(
        {
            "request_id": request_id,
            "client": client_key_hash,
            "provider": provider_used,
            "latency_ms": latency_ms,
            "breaker_state": breaker_state_value(),
            "tokens_in": prompt_tokens or 0,
            "tokens_out": completion_tokens or 0,
            "failure_reason": failure_reason,
        }
    )

    return result


# PUBLIC ENDPOINT (with global timeout)

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
                        "content": "Request timed out (global timeout).",
                    },
                    "finish_reason": "timeout",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }