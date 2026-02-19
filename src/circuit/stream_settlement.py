from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from circuit.cost import estimate_cost_usd
from circuit.quota import check_daily_quota, today_utc
from circuit.storage.sqlite import record_request, add_spend
from circuit.reliability.circuit_breaker import CircuitBreaker


class StreamSession:
    def __init__(
        self,
        *,
        request_id: str,
        client_key_hash: str,
        provider_name: str,
        model: str,
        breaker: CircuitBreaker,
    ) -> None:
        self.request_id = request_id
        self.client_key_hash = client_key_hash
        self.provider_name = provider_name
        self.model = model
        self.breaker = breaker

        self.started_at = datetime.now(timezone.utc)
        self.prompt_chars = 0
        self.generated_chars = 0
        self.status_code: int = 200


    def record_prompt(self, messages: Optional[List[Dict[str, Any]]]) -> None:
        if not messages:
            return

        total = 0
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                total += len(content)

        self.prompt_chars = total


    def record_chunk(self, text_chunk: str) -> None:
        if not text_chunk:
            return

        self.generated_chars += len(text_chunk)


    def _estimate_tokens(self) -> tuple[int, int]:
        # Conservative character-based estimate
        prompt_tokens = math.ceil(self.prompt_chars / 4)
        completion_tokens = math.ceil(self.generated_chars / 4)
        return prompt_tokens, completion_tokens

    def finalize_success(self) -> Dict[str, Any]:
        prompt_tokens, completion_tokens = self._estimate_tokens()

        cost_usd = estimate_cost_usd(
            self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        ok, spent, limit = check_daily_quota(self.client_key_hash, cost_usd)
        if not ok:
            self.status_code = 429
        else:
            if cost_usd > 0:
                add_spend(self.client_key_hash, today_utc(), cost_usd)

        latency_ms = int(
            (datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000
        )

        record_request(
            request_id=self.request_id,
            timestamp=self.started_at.isoformat(),
            provider=self.provider_name,
            model=self.model,
            status_code=self.status_code,
            latency_ms=latency_ms,
            tokens_input=prompt_tokens,
            tokens_output=completion_tokens,
            cost_usd=cost_usd,
        )

        self.breaker.record_success()

        return {
            "cost_usd": cost_usd,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "quota_ok": ok,
            "breaker_state": self.breaker.state.value,
        }

    def finalize_failure(self, status_code: int = 502) -> Dict[str, Any]:
        self.status_code = status_code

        prompt_tokens, completion_tokens = self._estimate_tokens()

        cost_usd = estimate_cost_usd(
            self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        latency_ms = int(
            (datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000
        )

        record_request(
            request_id=self.request_id,
            timestamp=self.started_at.isoformat(),
            provider=self.provider_name,
            model=self.model,
            status_code=status_code,
            latency_ms=latency_ms,
            tokens_input=prompt_tokens,
            tokens_output=completion_tokens,
            cost_usd=cost_usd,
        )

        if cost_usd > 0:
            add_spend(self.client_key_hash, today_utc(), cost_usd)

        self.breaker.record_failure()

        return {
            "cost_usd": cost_usd,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "breaker_state": self.breaker.state.value,
        }