from __future__ import annotations

import httpx


class OpenAIProvider:
    def __init__(self, api_key: str, base_url: str):
        timeout = httpx.Timeout(
            connect=2.0,
            read=10.0,
            write=5.0,
            pool=2.0,
        )

        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
        )

        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            limits=limits,
        )

    async def chat_completions(self, payload: dict) -> dict:
        response = await self.client.post(
            "/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        return response.json()