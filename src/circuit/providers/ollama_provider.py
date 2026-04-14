from __future__ import annotations

import httpx


class OllamaProvider:
    def __init__(self, base_url: str):
        timeout = httpx.Timeout(
            connect=1.0,
            read=15.0,
            write=5.0,
            pool=1.0,
        )

        limits = httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
        )

        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            limits=limits,
        )

    async def chat_completions(self, payload: dict) -> dict:
        response = await self.client.post(
            "/api/chat",
            json=payload,
        )
        response.raise_for_status()
        return response.json()