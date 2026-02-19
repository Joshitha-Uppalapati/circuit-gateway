import os
import time
from typing import Dict, Any

import httpx

from circuit.providers.base import ChatProvider
from circuit.models.errors import ProviderError


class OpenAIProvider(ChatProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        self.client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()

        try:
            response = await self.client.post(
                "/chat/completions",
                json=payload,
            )
        except httpx.TimeoutException:
            return {
                "error": ProviderError(
                    type="timeout",
                    message="OpenAI request timed out",
                    provider="openai",
                ).dict()
            }

        if response.status_code >= 400:
            return {
                "error": ProviderError(
                    type="upstream_error",
                    message=response.text,
                    provider="openai",
                    status_code=response.status_code,
                ).dict()
            }

        data = response.json()
        data["latency_ms"] = round((time.time() - start) * 1000, 2)
        return data