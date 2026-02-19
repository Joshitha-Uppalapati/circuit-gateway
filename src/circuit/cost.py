from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelPrice:
    input_per_1k: float
    output_per_1k: float


MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-4o": ModelPrice(input_per_1k=0.00, output_per_1k=0.00),
    "gpt-4o-mini": ModelPrice(input_per_1k=0.00, output_per_1k=0.00),
}


def estimate_cost_usd(model: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> float:
    price = MODEL_PRICES.get(model)
    if not price:
        return 0.0

    pt = float(prompt_tokens or 0)
    ct = float(completion_tokens or 0)

    return round((pt / 1000.0) * price.input_per_1k + (ct / 1000.0) * price.output_per_1k, 8)