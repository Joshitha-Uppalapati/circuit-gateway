import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def init_pool(database_url: str):
    global _pool

    _pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=5,
        max_size=20,
        command_timeout=10,
    )


async def close_pool():
    global _pool

    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Postgres pool not initialized")
    return _pool


async def record_request(
    request_id: str,
    timestamp: str,
    provider: str,
    model: str,
    status_code: int,
    latency_ms: float,
    tokens_input: int,
    tokens_output: int,
    cost_usd: float,
):
    pool = get_pool()

    async with pool.acquire() as conn:
        stmt = await conn.prepare(
            """
            INSERT INTO request_logs (
                id, ts, provider, model, status_code,
                latency_ms, tokens_in, tokens_out, cost_usd
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """
        )

        await stmt.execute(
            request_id,
            timestamp,
            provider,
            model,
            status_code,
            latency_ms,
            tokens_input,
            tokens_output,
            cost_usd,
        )


async def add_spend(client_key: str, day: str, amount: float):
    pool = get_pool()

    async with pool.acquire() as conn:
        stmt = await conn.prepare(
            """
            INSERT INTO daily_spend (client_key, day, amount)
            VALUES ($1,$2,$3)
            ON CONFLICT (client_key, day)
            DO UPDATE
            SET amount = daily_spend.amount + EXCLUDED.amount
            """
        )

        await stmt.execute(client_key, day, amount)


async def get_spend(client_key: str, day: str) -> float:
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT amount
            FROM daily_spend
            WHERE client_key = $1 AND day = $2
            """,
            client_key,
            day,
        )

        if not row:
            return 0.0

        return float(row["amount"])