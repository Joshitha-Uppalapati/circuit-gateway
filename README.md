# circuit-gateway

LLM APIs break in production in subtle ways.

I got tired of systems looking great in demos but failing unpredictably when users actually rely on them. Dropped requests, provider latency spikes, and the headache of accurately counting tokens during streaming responses all quietly degrade the user experience. 

Circuit is a lightweight, opinionated gateway that sits between your application and the LLM provider. It handles the gritty infrastructure tasks so the core product can remain reliable.

## Request Flow

```text
User -> Gateway -> Provider
         |
    request logged
    quota checked
    breaker validated
         |
    streaming handled
    final usage recorded
```
Handles rate limiting, quota enforcement, and circuit breaking before hitting the provider.

---

## Handling Failure Scenarios
The hardest part of LLM infrastructure is when things partially fail. For example, if a provider drops mid-stream:
- Partial response is tracked and saved to SQLite
- The request is marked as failed
- The circuit breaker state is updated to prevent cascading failures

### Example: Circuit Breaker Tripped
When the upstream provider is degrading, Circuit stops sending requests and instantly returns a structured 503 to protect the system:
```json
{
  "error": {
    "code": "service_unavailable",
    "message": "Upstream provider temporarily unavailable"
  }
}
```

---

## What's implemented
- Stream Settlement: Parses SSE chunks to track tokens and costs in real-time without breaking the stream.
- Circuit Breaker: Trips and returns 503s when upstream is unhealthy.
- Stateful Quotas: Enforces daily USD spend limits per client using SQLite.
- Observability: Attaches x-request-id and logs latency, cost, and provider health.
- Provider Switching: Easily swap between a local mock and OpenAI.

## Local setup
**Requirements**
- Python 3.12+
- uvicorn
**Install**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Environment
Create a `.env` file. The database is created automatically at `data/circuit.db`.
```bash
PROVIDER=MOCK
CIRCUIT_API_KEYS=test-key
CIRCUIT_DAILY_USD_LIMIT=10.0
```

**Run**
```bash
uvicorn circuit.main:app --reload --port 8080
```

## JSON Mode
```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}]}'
```

## Streaming Mode
```bash
curl -N http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello streaming"}],"stream":true}'
```

## Inspect database
```bash
sqlite3 data/circuit.db
.tables
SELECT request_id, status_code, tokens_input, tokens_output, cost_usd
FROM requests
ORDER BY timestamp DESC
LIMIT 10;
```

**Provider switching**
- PROVIDER=MOCK uses the mock provider (useful for tests and local dev)
- PROVIDER=OPENAI uses the real OpenAI provider (requires OPENAI_API_KEY)

Example .env for OpenAI:
```bash
PROVIDER=OPENAI
CIRCUIT_API_KEYS=test-key
CIRCUIT_DAILY_USD_LIMIT=10.0
OPENAI_API_KEY=sk-...
```

---

## Current Focus (Phase 2)
Moving from basic routing to resilience. Currently working on adding intelligent retries, exponential backoff, and automatic fallback providers (e.g., routing to Anthropic if OpenAI throws 500s).
