from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from circuit.middleware.auth import AuthMiddleware
from circuit.middleware.logging import LoggingMiddleware
from circuit.middleware.request_id import RequestIDMiddleware
from circuit.providers.factory import get_chat_provider
from circuit.models.openai_compat import ChatCompletionRequest
from circuit.cost import estimate_cost_usd
from circuit.quota import check_daily_quota, today_utc
from circuit.storage.sqlite import init_db, record_request, add_spend
from circuit.reliability.circuit_breaker import CircuitBreaker
from circuit.reliability.rate_limiter import RateLimiter
from circuit.stream_settlement import StreamSession


app = FastAPI()

app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)

provider = get_chat_provider()
breaker = CircuitBreaker()
rate_limiter = RateLimiter(capacity=20, refill_rate_per_sec=5)


@app.on_event("startup")
async def _startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    client_key_hash = getattr(request.state, "client_key_hash", "unknown")
    request_id = getattr(request.state, "request_id", "unknown")

    # REAL-TIME RATE LIMIT 
    if not rate_limiter.allow(client_key_hash):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests. Slow down.",
                }
            },
        )

    payload = body.model_dump()
    model = payload.get("model", "unknown")

    # PRE-COST QUOTA CHECK
    max_tokens = payload.get("max_tokens") or 0
    pre_cost = estimate_cost_usd(model, prompt_tokens=0, completion_tokens=int(max_tokens))

    ok, spent, limit = check_daily_quota(client_key_hash, pre_cost)
    if not ok:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "quota_exceeded",
                    "message": f"Daily spend limit reached. spent=${spent:.4f} limit=${limit:.4f}",
                }
            },
        )

    # STREAMING MODE
    if body.stream:
        if not breaker.allow_request():
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "service_unavailable",
                        "message": "Upstream provider temporarily unavailable",
                    }
                },
            )

        session = StreamSession(
            request_id=request_id,
            client_key_hash=client_key_hash,
            provider_name=type(provider).__name__,
            model=model,
            breaker=breaker,
        )

        session.record_prompt(payload.get("messages"))

        async def event_stream():
            try:
                async for chunk in provider.chat_completions_stream(payload):
                    text = ""

                    # Provider yielded dict
                    if isinstance(chunk, dict):
                        text = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )

                    # Provider yielded bytes
                    elif isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8")

                    # Provider yielded SSE string
                    if isinstance(chunk, str):
                        if chunk.startswith("data:"):
                            data_str = chunk.replace("data:", "", 1).strip()

                            if data_str != "[DONE]":
                                try:
                                    parsed = json.loads(data_str)
                                    text = (
                                        parsed.get("choices", [{}])[0]
                                        .get("delta", {})
                                        .get("content", "")
                                    )
                                except Exception:
                                    text = ""

                    session.record_chunk(text)
                    yield chunk

                session.finalize_success()

            except Exception:
                session.finalize_failure()
                raise

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # JSON MODE
    if not breaker.allow_request():
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "service_unavailable",
                    "message": "Upstream provider temporarily unavailable",
                }
            },
        )

    result = await provider.chat_completions(payload)

    if isinstance(result, dict) and "error" in result:
        breaker.record_failure()

        record_request(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=type(provider).__name__,
            model=model,
            status_code=502,
            latency_ms=int(result.get("latency_ms") or 0),
            tokens_input=None,
            tokens_output=None,
            cost_usd=None,
        )

        return JSONResponse(status_code=502, content=result)

    breaker.record_success()

    usage = (result or {}).get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    ok2, spent2, limit2 = check_daily_quota(client_key_hash, cost_usd)
    if not ok2:
        record_request(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=type(provider).__name__,
            model=model,
            status_code=429,
            latency_ms=int(result.get("latency_ms") or 0),
            tokens_input=prompt_tokens,
            tokens_output=completion_tokens,
            cost_usd=cost_usd,
        )

        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "quota_exceeded",
                    "message": f"Daily spend limit reached. spent=${spent2:.4f} limit=${limit2:.4f}",
                }
            },
        )

    record_request(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        provider=type(provider).__name__,
        model=model,
        status_code=200,
        latency_ms=int(result.get("latency_ms") or 0),
        tokens_input=prompt_tokens,
        tokens_output=completion_tokens,
        cost_usd=cost_usd,
    )

    if cost_usd > 0:
        add_spend(client_key_hash, today_utc(), cost_usd)

    result["circuit"] = {
        "request_id": request_id,
        "client_key_hash": client_key_hash,
        "cost_usd": cost_usd,
        "breaker_state": breaker.state.value,
    }

    return result