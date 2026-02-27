from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from circuit.middleware.auth import AuthMiddleware
from circuit.middleware.latency import LatencyMiddleware
from circuit.middleware.logging import LoggingMiddleware
from circuit.middleware.request_id import RequestIDMiddleware

from circuit.cost import estimate_cost_usd
from circuit.models.openai_compat import ChatCompletionRequest
from circuit.observability.metrics import metrics
from circuit.providers.factory import get_chat_provider
from circuit.providers.ollama_provider import OllamaProvider
from circuit.reliability.circuit_breaker import CircuitBreaker
from circuit.reliability.rate_limiter import RateLimiter
from circuit.reliability.redis_rate_limiter import RedisRateLimiter
from circuit.reliability.retry import with_retries
from circuit.storage.redis_client import get_redis_client
from circuit.storage.sqlite import init_db, record_request
from circuit.tokenizer import count_tokens_from_messages, count_tokens_from_text


app = FastAPI()

app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(LatencyMiddleware)

provider = get_chat_provider()
fallback_provider = OllamaProvider()

breaker = CircuitBreaker()

# Rate limit config
RL_CAPACITY = 20
RL_REFILL_PER_SEC = 5


redis_client = get_redis_client()
if redis_client:
    rate_limiter = RedisRateLimiter(
        redis_client=redis_client,
        capacity=RL_CAPACITY,
        refill_rate_per_sec=RL_REFILL_PER_SEC,
    )
else:
    rate_limiter = RateLimiter(
        capacity=RL_CAPACITY,
        refill_rate_per_sec=RL_REFILL_PER_SEC,
    )


@app.on_event("startup")
async def _startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def get_metrics(client: str | None = None):
    return metrics.snapshot(client)


@app.get("/metrics/prometheus")
async def prometheus_metrics():
    return Response(content=metrics.prometheus(), media_type="text/plain")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    client_key_hash = getattr(request.state, "client_key_hash", "unknown")
    request_id = getattr(request.state, "request_id", "unknown")

    # Rate limiting
    if not rate_limiter.allow(client_key_hash):
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
        )

    metrics.inc("total_requests", client=client_key_hash)

    payload = body.model_dump()
    model = payload.get("model", "unknown")
    provider_used = type(provider).__name__

    # Primary (with retries)
    try:
        result = await with_retries(lambda: provider.chat_completions(payload))

        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(result["error"].get("message", "provider error"))

    except Exception as e:
        print("PRIMARY FAILED:", repr(e))

        # Fallback (Ollama)
        try:
            result = await fallback_provider.chat_completions(payload)

            if isinstance(result, dict) and "error" in result:
                raise RuntimeError(result["error"].get("message", "fallback error"))

            provider_used = type(fallback_provider).__name__
            metrics.inc("fallback_hits", client=client_key_hash)

        except Exception as e:
            print("FALLBACK FAILED:", repr(e))

            breaker.record_failure()
            metrics.inc("total_503", client=client_key_hash)

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

            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "fallback_failed",
                        "message": "Primary and fallback providers both failed",
                    }
                },
            )

    # Success
    breaker.record_success()

    messages = payload.get("messages", [])
    prompt_tokens = count_tokens_from_messages(model, messages)

    assistant_content = (
        result.get("choices", [{}])[0].get("message", {}).get("content", "")
    )
    completion_tokens = count_tokens_from_text(model, assistant_content)

    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    metrics.inc("total_success", client=client_key_hash)
    metrics.inc("total_tokens_input", prompt_tokens, client=client_key_hash)
    metrics.inc("total_tokens_output", completion_tokens, client=client_key_hash)
    metrics.inc("total_cost_usd", cost_usd, client=client_key_hash)

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

    result["circuit"] = {
        "request_id": request_id,
        "client_key_hash": client_key_hash,
        "cost_usd": cost_usd,
        "breaker_state": breaker.state.value,
    }

    return result