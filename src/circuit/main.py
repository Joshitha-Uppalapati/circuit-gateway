from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from circuit.middleware.auth import AuthMiddleware
from circuit.middleware.logging import LoggingMiddleware
from circuit.middleware.request_id import RequestIDMiddleware
from circuit.middleware.latency import LatencyMiddleware

from circuit.providers.factory import get_chat_provider
from circuit.models.openai_compat import ChatCompletionRequest
from circuit.cost import estimate_cost_usd
from circuit.storage.sqlite import init_db, record_request
from circuit.reliability.circuit_breaker import CircuitBreaker
from circuit.reliability.rate_limiter import RateLimiter
from circuit.reliability.retry import with_retries
from circuit.observability.metrics import metrics
from circuit.tokenizer import (
    count_tokens_from_messages,
    count_tokens_from_text,
)


app = FastAPI()

app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(LatencyMiddleware)

provider = get_chat_provider()
breaker = CircuitBreaker()
rate_limiter = RateLimiter(capacity=20, refill_rate_per_sec=5)


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
    return Response(
        content=metrics.prometheus(),
        media_type="text/plain",
    )


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

    # Retry wrapper
    try:
        result = await with_retries(
            lambda: provider.chat_completions(payload)
        )
    except Exception:
        breaker.record_failure()

        record_request(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=type(provider).__name__,
            model=model,
            status_code=503,
            latency_ms=0,
            tokens_input=0,
            tokens_output=0,
            cost_usd=0.0,
        )

        metrics.inc("total_503", client=client_key_hash)

        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "retry_exhausted",
                    "message": "Upstream failed after retries",
                }
            },
        )

    # Handle provider error AFTER retry
    if isinstance(result, dict) and "error" in result:
        code = result["error"].get("code")

        breaker.record_failure()

        record_request(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=type(provider).__name__,
            model=model,
            status_code=503,
            latency_ms=0,
            tokens_input=0,
            tokens_output=0,
            cost_usd=0.0,
        )

        metrics.inc("total_503", client=client_key_hash)

        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": code or "provider_error",
                    "message": result["error"].get("message", "Upstream error"),
                }
            },
        )

    # Success path
    breaker.record_success()

    messages = payload.get("messages", [])
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

    record_request(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        provider=type(provider).__name__,
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