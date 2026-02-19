from typing import Optional, Dict
from circuit.cost.pricing import MODEL_PRICING_USD_PER_1K


def calculate_cost(
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> Optional[float]:
    if model not in MODEL_PRICING_USD_PER_1K:
        return None

    if prompt_tokens is None or completion_tokens is None:
        return None

    pricing = MODEL_PRICING_USD_PER_1K[model]

    cost = (
        (prompt_tokens / 1000) * pricing["prompt"]
        + (completion_tokens / 1000) * pricing["completion"]
    )

    return round(cost, 6)