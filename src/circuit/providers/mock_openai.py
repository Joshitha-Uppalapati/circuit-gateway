from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, Any


class MockOpenAIProvider:
    def __init__(self) -> None:
        self.failures_left = 5

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.perf_counter()

        if self.failures_left > 0:
            self.failures_left -= 1
            await asyncio.sleep(0.05)
            return {
                "error": {
                    "code": "server_error",
                    "message": "forced failure",
                }
            }

        await asyncio.sleep(0.01)

        messages = payload.get("messages", [])
        user_content = ""

        for m in reversed(messages):
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break

        result = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", "gpt-4o"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"Mock response to: {user_content}",
                    },
                    "finish_reason": "stop",
                }
            ],
        }

        result["latency_ms"] = (time.perf_counter() - start) * 1000
        return result