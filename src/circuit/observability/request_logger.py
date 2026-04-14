import logging

from circuit.storage.postgres_client import get_pool

logger = logging.getLogger(__name__)


async def log_request(data: dict) -> None:
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO request_logs (
                    id, client, provider, latency_ms, breaker_state,
                    tokens_in, tokens_out, failure_reason, input_size, used_fallback
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                """,
                data["request_id"], data["client"], data["provider"],
                data["latency_ms"], data["breaker_state"],
                data["tokens_in"], data["tokens_out"], data["failure_reason"],
                data.get("input_size"), data.get("used_fallback"),
            )
    except Exception as e:
        logger.warning("request log failed: %s", e)