from __future__ import annotations

import time
import uuid
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from circuit.middleware.auth import AuthMiddleware
from circuit.storage.redis_client import get_redis_client
from circuit.reliability.redis_rate_limiter import RedisRateLimiter
from circuit.reliability.redis_circuit_breaker import RedisCircuitBreaker, BreakerConfig

from circuit.providers.mock_openai import MockOpenAIProvider
from circuit.providers.ollama_provider import OllamaProvider

from circuit.observability.metrics import metrics
from circuit.observability.request_logger import log_request

from circuit.reliability.retry import with_retries, DEFAULT_RETRY
from circuit.reliability.timeout import with_timeout

from circuit.cost.calculator import calculate_cost


app = FastAPI()
app.add_middleware(AuthMiddleware)


# PROVIDERS
try:
    primary_provider = MockOpenAIProvider()
except Exception as e:
    print("PRIMARY INIT FAILED:", e)
    primary_provider = None

fallback_provider = OllamaProvider()


# REDIS
redis_client = get_redis_client()


# RATE LIMITER
if redis_client:
    rate_limiter = RedisRateLimiter(
        redis_client=redis_client,
        capacity=20,
        refill_rate_per_sec=5,
    )
else:
    rate_limiter = None


# CIRCUIT BREAKER
if redis_client:
    breaker = RedisCircuitBreaker(
        redis_client=redis_client,
        name="primary",
        config=BreakerConfig(
            failure_threshold=3,
            window_seconds=30,
            cooldown_seconds=20,
        ),
    )
else:
    breaker = None


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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    start = time.time()
    request_id = str(uuid.uuid4())

    client_key_hash = request.state.client_key_hash
    payload = await request.json()

    failure_reason = None
    provider_used = "primary"

    # RATE LIMIT
    if rate_limiter and not rate_limiter.allow(client_key_hash):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests",
                }
            },
        )

    metrics.inc("total_requests", client=client_key_hash)

    result = None
    try_primary = primary_provider is not None

    # CIRCUIT CHECK
    if try_primary and breaker and not breaker.allow_request():
        print("CIRCUIT OPEN: skipping primary")
        try_primary = False

    # PRIMARY CALL
    if try_primary:
        try:
            result = await with_retries(
                lambda: with_timeout(
                    lambda: primary_provider.chat_completions(payload),
                    timeout_seconds=0.8,
                ),
                config=DEFAULT_RETRY,
            )

            if not result or "choices" not in result:
                raise RuntimeError("invalid response from primary")

            if breaker:
                breaker.record_success()

        except Exception as e:
            print(f"BREAKER STATE: {breaker.state.value if breaker else 'disabled'}")

            err = str(e).lower()
            if "invalid response" in err:
                failure_reason = "invalid_response"
            elif "timeout" in err:
                failure_reason = "timeout"
            elif "forced failure" in err:
                failure_reason = "forced_failure"
            else:
                failure_reason = "provider_error"

            if breaker:
                breaker.record_failure()

            result = None

    # FALLBACK
    if result is None:
        provider_used = "fallback"

        task = asyncio.create_task(
            fallback_provider.chat_completions(payload)
        )

        try:
            result = await asyncio.wait_for(task, timeout=1.2)

        except asyncio.TimeoutError:
            task.cancel()

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
                    "breaker_state": breaker.state.value if breaker else "disabled",
                    "provider": "timeout",
                },
            }

    # SUCCESS
    latency_ms = (time.time() - start) * 1000

    metrics.observe_latency(latency_ms)
    metrics.inc("total_success", client=client_key_hash)

    usage = result.get("usage", {})
    model = result.get("model", "unknown")

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    # FIXED COST CALCULATION
    cost = calculate_cost(model, prompt_tokens, completion_tokens)
    cost = cost if cost is not None else 0.0

    metrics.inc("total_tokens_input", prompt_tokens or 0)
    metrics.inc("total_tokens_output", completion_tokens or 0)

    result["latency_ms"] = latency_ms
    result["circuit"] = {
        "request_id": request_id,
        "client_key_hash": client_key_hash,
        "cost_usd": cost,
        "breaker_state": breaker.state.value if breaker else "disabled",
        "provider": provider_used,
    }

    result["meta"] = {
        "failure_reason": failure_reason,
        "used_fallback": provider_used == "fallback",
    }

    log_request(
        {
            "request_id": request_id,
            "client": client_key_hash,
            "provider": provider_used,
            "latency_ms": latency_ms,
            "breaker_state": breaker.state.value if breaker else "disabled",
            "tokens_in": prompt_tokens or 0,
            "tokens_out": completion_tokens or 0,
            "failure_reason": failure_reason,
        }
    )

    return result