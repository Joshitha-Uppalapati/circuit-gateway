# ADR-001: Provider fallback and reliability strategy

## Context
LLM providers fail in production in subtle ways. Timeouts, invalid responses, and upstream instability are normal once traffic is real.

## Decision
The gateway uses retries for transient failures, timeout guards to fail fast, a circuit breaker to stop sending traffic to a failing provider, and a fallback provider to preserve service continuity.

Fallback remains inline in `main.py` instead of using a shared helper. The request path is easier to debug when the primary, breaker, retry, timeout, and fallback flow stay visible in one place.

## Tradeoffs
Inline fallback adds some repetition, but the control flow is explicit. This matters more here than abstraction.

## Result
The request path is easier to reason about, provider failures degrade more cleanly, and the gateway behavior matches the reliability claims in the repo.