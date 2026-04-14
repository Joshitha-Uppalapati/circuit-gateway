# circuit-gateway

Circuit is an LLM gateway designed to handle reliability concerns in multi-agent systems. It sits between application code and upstream model providers, enforcing rate limits, managing failure with a circuit breaker, routing to a local fallback (Ollama), and tracking cost based on actual token usage.

The system focuses on two failure modes that show up in production: upstream instability and uncontrolled API spend.

---

## Why I Built This

In multi-agent workflows, failures are rarely clean. A provider might degrade, time out intermittently, or return partial results. Without structure, this leads to cascading failures across agents.

At the same time, cost becomes unpredictable. Token usage accumulates across retries, fallback paths, and long-running chains. Without accurate accounting, it is easy to exceed budget limits without visibility.

Circuit addresses both:

- Prevents cascading failures using a three-state circuit breaker
- Routes traffic to a local fallback when upstream becomes unreliable
- Tracks token usage and cost per request for auditability and quota enforcement

---

## Quick Start

```bash
docker compose up --build
```

The API will be available at:
```
http://localhost:8000
```

Health check:
```bash
curl http://localhost:8000/health
```

---

## Demo: Circuit Breaker Failover

To observe failure handling and recovery:
```bash
python3 demo_breaker.py
```

This script simulates upstream failures and shows:
- Initial failures hitting the provider
- Circuit transitioning to OPEN (fast 503 responses)
- Cooldown period
- HALF_OPEN probe request
- Recovery back to CLOSED state

You should see latency shift from slow (real calls) to fast (short-circuit), then back to normal after recovery.

## Key Components
- CircuitBreaker: Three-state FSM (closed, open, half_open)
- RateLimiter: Token bucket per client
- Retry: Exponential backoff for transient failures
- Cost Tracking: Token-based settlement using tiktoken
- Storage: SQLite-backed request logging and quota tracking
- Fallback: Local Ollama provider when upstream is unavailable

## Notes

This implementation runs as a single-process service. State for rate limiting and circuit breaking is in-memory. A production deployment would externalize state (e.g., Redis) to support multiple workers.


---

## docs/decisions/ADR-001-rate-limiter.md

```markdown
# ADR 001: In-Memory Token Bucket for Rate Limiting (Phase 1)

## Context

The system requires per-client rate limiting to prevent abuse and control request bursts. The design must be simple enough to support rapid iteration during early development while still modeling realistic behavior.

At the same time, the system is currently deployed as a single-process FastAPI application without horizontal scaling.

## Decision

Use an in-memory token bucket implementation keyed by client identifier.

Each client is assigned a TokenBucket instance stored in an OrderedDict with a bounded size to prevent unbounded memory growth. Buckets are created on demand and evicted using LRU semantics.

## Consequences

### Positive

- Zero external dependencies
- Minimal latency overhead
- Simple to reason about and test
- Fast to implement for MVP

### Negative

- State is not shared across processes
- Not suitable for multi-worker or distributed deployments
- Rate limits reset on process restart

### Future Work

In a multi-worker or distributed deployment, this design should be replaced with a shared backend such as Redis to ensure consistent enforcement across instances.
```

---

## docs/decisions/ADR-002-circuit-breaker.md

```markdown
# ADR 002: Three-State Circuit Breaker with Local Fallback

## Context

Upstream LLM providers can exhibit intermittent failures, latency spikes, or full outages. In multi-agent systems, these failures propagate quickly and can stall entire workflows.

A naive approach is to retry or return errors directly to the caller. This leads to increased latency, higher cost, and poor system stability.

## Decision

Implement a three-state circuit breaker with the following behavior:

- CLOSED: All requests are sent to the primary provider
- OPEN: Requests are short-circuited and routed to a local fallback (Ollama)
- HALF_OPEN: A single probe request is allowed to test recovery

Instead of dropping requests during the OPEN state, the system routes them to a local model.

## Consequences

### Positive

- Prevents cascading failures during upstream outages
- Maintains partial service availability via fallback
- Reduces latency during outage by short-circuiting failing calls
- Enables controlled recovery via HALF_OPEN probe

### Negative

- Fallback responses may differ in quality from primary provider
- Additional operational complexity in maintaining local model
- Requires careful tuning of thresholds and cooldown periods

### Rationale

Routing to a fallback preserves system functionality under failure conditions. In many applications, a degraded response is preferable to a failed request.

This design aligns with real-world requirements where availability is prioritized over perfect output quality.
```
