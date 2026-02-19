from __future__ import annotations

from datetime import datetime, timezone

from circuit.config import settings
from circuit.storage.sqlite import get_daily_spend


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_daily_quota(client_key_hash: str, additional_cost_usd: float) -> tuple[bool, float, float]:
    date = today_utc()
    spent = float(get_daily_spend(client_key_hash, date))
    limit = float(settings.CIRCUIT_DAILY_USD_LIMIT)

    projected = spent + float(additional_cost_usd)
    allowed = projected <= limit
    return allowed, spent, limit