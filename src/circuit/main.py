from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from circuit.config import settings
from circuit.cost import estimate_cost_usd
from circuit.middleware.auth import AuthMiddleware
from circuit.middleware.latency import LatencyMiddleware
from circuit.middleware.logging import LoggingMiddleware, setup_logging
from circuit.middleware.request_id import RequestIDMiddleware
from circuit.middleware.timeout import TimeoutMiddleware
from circuit.models.openai_compat import ChatCompletionRequest
from circuit.observability.metrics import metrics
from circuit.observability.request_logger import log_request
from circuit.providers.factory import get_active_providers, get_chat_provider
from circuit.providers.ollama_provider import OllamaProvider
from circuit.quota.enforcer import enforce_quota
from circuit.reliability.redis_circuit_breaker import RedisCircuitBreaker
from circuit.reliability.redis_rate_limiter import RedisRateLimiter
from circuit.reliability.retry import with_retries
from circuit.storage.postgres_client import (
    add_spend,
    close_pool,
    get_pool,
    init_pool,
    record_request,
)
from circuit.storage.redis_client import get_redis_client
from circuit.storage.task_tracker import drain, spawn
from circuit.tokenizer import count_tokens_from_messages, count_tokens_from_text


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool(settings.DATABASE_URL)
    yield
    await drain()

    for provider in get_active_providers():
        client = getattr(provider, "client", None)
        if client:
            await client.aclose()

    await close_pool()


app = FastAPI(lifespan=lifespan)

app.add_middleware(TimeoutMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(LatencyMiddleware)

provider = get_chat_provider()
fallback_provider = OllamaProvider(base_url=settings.OLLAMA_BASE_URL)

redis_conn = get_redis_client()
breaker = RedisCircuitBreaker("primary")
rate_limiter = RedisRateLimiter(redis_conn, max_capacity=20, refill_rate=5.0)


@app.get("/health")
async def health():
    redis_status = "up"
    postgres_status = "up"

    try:
        redis = get_redis_client()
        if redis is None:
            raise RuntimeError("redis unavailable")
        pong = redis.ping()
        if asyncio.iscoroutine(pong):
            await pong
    except Exception:
        redis_status = "down"

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
    except Exception:
        postgres_status = "down"

    if redis_status == "up" and postgres_status == "up":
        return {
            "status": "healthy",
            "redis": "up",
            "postgres": "up",
        }

    return JSONResponse(
        status_code=503,
        content={
            "status": "degraded",
            "redis": redis_status,
            "postgres": postgres_status,
        },
    )


@app.get("/metrics")
async def get_metrics(client: str | None = None):
    return metrics.snapshot(client)


@app.get("/metrics/prometheus")
async def prometheus_metrics():
    return Response(
        content=metrics.prometheus(),
        media_type="text/plain",
    )


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
            {"id": "gpt-3.5-turbo", "object": "model", "owned_by": "openai"},
            {"id": "ollama-llama3", "object": "model", "owned_by": "ollama"},
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    payload: ChatCompletionRequest,
):
    request_id = getattr(request.state, "request_id", "unknown")
    client_key_hash = enforce_quota(request, estimated_cost=0.0)

    rate_limit = rate_limiter.allow(client_key_hash)
    if not rate_limit["allowed"]:
        metrics.inc("total_429", client=client_key_hash)
        metrics.inc("rate_limit_hits", client=client_key_hash)
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests. Slow down.",
                }
            },
            headers=rate_limiter.headers(rate_limit),
        )

    if not breaker.allow_request():
        metrics.inc("total_503", client=client_key_hash)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "circuit_open",
                    "message": "Upstream unavailable. Try again later.",
                }
            },
        )

    metrics.inc("total_requests", client=client_key_hash)

    payload_dict = payload.model_dump()
    model = payload_dict.get("model", "unknown")
    provider_used = type(provider).__name__

    async def _primary_call():
        return await provider.chat_completions(payload_dict)

    try:
        result = await with_retries(_primary_call)

        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(result["error"].get("message"))

    except Exception:
        try:
            result = await fallback_provider.chat_completions(payload_dict)

            if isinstance(result, dict) and "error" in result:
                raise RuntimeError(result["error"].get("message"))

            provider_used = type(fallback_provider).__name__
            metrics.inc("fallback_hits", client=client_key_hash)

        except Exception:
            breaker.record_failure()

            spawn(
                record_request(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    provider=provider_used,
                    model=model,
                    status_code=503,
                    latency_ms=0,
                    tokens_input=0,
                    tokens_output=0,
                    cost_usd=0.0,
                )
            )

            metrics.inc("total_503", client=client_key_hash)

            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "fallback_failed",
                        "message": "Primary and fallback providers both failed",
                    }
                },
            )

    breaker.record_success()

    messages = payload_dict.get("messages", [])
    prompt_tokens = count_tokens_from_messages(model, messages)

    assistant_content = (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    completion_tokens = count_tokens_from_text(model, assistant_content)
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    metrics.inc("total_success", client=client_key_hash)
    metrics.inc("total_tokens_input", prompt_tokens, client=client_key_hash)
    metrics.inc("total_tokens_output", completion_tokens, client=client_key_hash)
    metrics.inc("total_cost_usd", cost_usd, client=client_key_hash)

    spawn(
        record_request(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=provider_used,
            model=model,
            status_code=200,
            latency_ms=result.get("latency_ms", 0),
            tokens_input=prompt_tokens,
            tokens_output=completion_tokens,
            cost_usd=cost_usd,
        )
    )

    today = datetime.now(timezone.utc).date().isoformat()
    spawn(add_spend(client_key_hash, today, cost_usd))

    log_data = {
        "request_id": request_id,
        "client": client_key_hash,
        "provider": provider_used,
        "latency_ms": result.get("latency_ms", 0),
        "breaker_state": breaker._get_value(breaker._state_key()),
        "tokens_in": prompt_tokens,
        "tokens_out": completion_tokens,
        "failure_reason": None,
        "input_size": len(messages),
        "used_fallback": provider_used != type(provider).__name__,
    }
    spawn(log_request(log_data))

    result["circuit"] = {
        "request_id": request_id,
        "client_key_hash": client_key_hash,
        "cost_usd": cost_usd,
    }

    headers = rate_limiter.headers(rate_limit)
    return JSONResponse(content=result, headers=headers)