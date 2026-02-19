# circuit-gateway

A small FastAPI gateway that exposes an OpenAI-compatible `/v1/chat/completions` endpoint and adds:
- request IDs + structured logging
- API key auth
- provider switching (mock vs OpenAI)
- cost + token accounting (estimation-friendly)
- daily spend quota enforcement
- circuit breaker protection
- streaming support with stream settlement into SQLite

## What’s implemented

### Endpoints
- `GET /health`
- `POST /v1/chat/completions` (OpenAI-compatible shape)

### Features
- **Auth**: `Authorization: Bearer <key>` checked against `CIRCUIT_API_KEYS`
- **Request IDs**: attaches `x-request-id` and logs it
- **SQLite persistence**
  - `requests` table stores: request_id, model, status, latency, tokens, cost
  - `quota_usage` stores per-client daily spend
- **Quota enforcement**: blocks once daily USD limit is reached
- **Circuit breaker**: returns 503 when upstream is unhealthy
- **Streaming mode**: streams SSE chunks and still records the request on completion (or failure)

## Local setup

### Requirements
- Python 3.12+
- `uvicorn`

### Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Environment
Create a .env file
```bash
PROVIDER=MOCK
CIRCUIT_API_KEYS=test-key
CIRCUIT_DAILY_USD_LIMIT=10.0
```

The database file is created automatically at:
```bash
data/circuit.db
```

### Run
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

### Provider switching
- PROVIDER=MOCK uses the mock provider (useful for tests + local dev)
- PROVIDER=OPENAI uses the real OpenAI provider (requires OPENAI_API_KEY)
Example .env for OpenAI:
```bash
PROVIDER=OPENAI
CIRCUIT_API_KEYS=test-key
CIRCUIT_DAILY_USD_LIMIT=10.0
OPENAI_API_KEY=sk-...
```