from __future__ import annotations

from typing import Optional

from circuit.cost.pricing import MODEL_PRICING_USD_PER_1K


def estimate_cost_usd(
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> float:
    pricing = MODEL_PRICING_USD_PER_1K.get(model)
    if not pricing:
        return 0.0

    pt = float(prompt_tokens or 0)
    ct = float(completion_tokens or 0)

    return round(
        (pt / 1000.0) * pricing["prompt"]
        + (ct / 1000.0) * pricing["completion"],
        8,
    )