CREATE TABLE IF NOT EXISTS request_logs (
    id TEXT PRIMARY KEY,
    ts TIMESTAMPTZ,
    provider TEXT,
    model TEXT,
    status_code INT,
    latency_ms DOUBLE PRECISION,
    tokens_in INT,
    tokens_out INT,
    cost_usd DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS daily_spend (
    client_key TEXT,
    day DATE,
    amount DOUBLE PRECISION,
    PRIMARY KEY (client_key, day)
);

CREATE INDEX IF NOT EXISTS idx_daily_spend_client_day
ON daily_spend (client_key, day);

CREATE INDEX IF NOT EXISTS idx_request_logs_ts
ON request_logs (ts DESC);

CREATE INDEX IF NOT EXISTS idx_request_logs_provider_ts
ON request_logs (provider, ts DESC);