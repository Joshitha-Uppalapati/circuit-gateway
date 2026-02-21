from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict

from circuit.tokenizer import (
    count_tokens_from_messages,
    count_tokens_from_text,
)
from circuit.cost import estimate_cost_usd
from circuit.storage.sqlite import record_request, add_spend
from circuit.quota import check_daily_quota, today_utc


class StreamSession:
    def __init__(
        self,
        request_id: str,
        client_key_hash: str,
        provider_name: str,
        model: str,
        breaker,
    ):
        self.request_id = request_id
        self.client_key_hash = client_key_hash
        self.provider_name = provider_name
        self.model = model
        self.breaker = breaker

        self.messages: List[Dict] = []
        self.output_chunks: List[str] = []

        self.start_time = datetime.now(timezone.utc)

    def record_prompt(self, messages: List[Dict]):
        self.messages = messages or []

    def record_chunk(self, text: str):
        if text:
            self.output_chunks.append(text)

    def finalize_success(self):
        end_time = datetime.now(timezone.utc)
        latency_ms = (end_time - self.start_time).total_seconds() * 1000

        full_output = "".join(self.output_chunks)

        # REAL TOKEN COUNTING (no more char hacks)
        prompt_tokens = count_tokens_from_messages(self.model, self.messages)
        completion_tokens = count_tokens_from_text(self.model, full_output)

        cost_usd = estimate_cost_usd(
            self.model,
            prompt_tokens,
            completion_tokens,
        )

        # Final quota check
        ok, spent, limit = check_daily_quota(
            self.client_key_hash,
            cost_usd,
        )

        if ok and cost_usd > 0:
            add_spend(
                self.client_key_hash,
                today_utc(),
                cost_usd,
            )

        record_request(
            request_id=self.request_id,
            timestamp=self.start_time.isoformat(),
            provider=self.provider_name,
            model=self.model,
            status_code=200,
            latency_ms=int(latency_ms),
            tokens_input=prompt_tokens,
            tokens_output=completion_tokens,
            cost_usd=cost_usd,
        )

        self.breaker.record_success()

    def finalize_failure(self):
        end_time = datetime.now(timezone.utc)
        latency_ms = (end_time - self.start_time).total_seconds() * 1000

        record_request(
            request_id=self.request_id,
            timestamp=self.start_time.isoformat(),
            provider=self.provider_name,
            model=self.model,
            status_code=502,
            latency_ms=int(latency_ms),
            tokens_input=None,
            tokens_output=None,
            cost_usd=None,
        )

        self.breaker.record_failure()