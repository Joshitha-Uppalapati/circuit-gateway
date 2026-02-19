import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from circuit.quota.limits import DEFAULT_DAILY_USD_LIMIT
from circuit.storage.sqlite import get_daily_spend


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()[:8]


def enforce_quota(request: Request, estimated_cost: float = 0.0) -> str:
    auth = request.headers.get("authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")

    raw_key = auth.replace("Bearer ", "")
    key_hash = hash_key(raw_key)

    today = datetime.now(timezone.utc).date().isoformat()
    spent = get_daily_spend(key_hash, today)

    if spent + estimated_cost > DEFAULT_DAILY_USD_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Daily quota exceeded",
        )

    return key_hash