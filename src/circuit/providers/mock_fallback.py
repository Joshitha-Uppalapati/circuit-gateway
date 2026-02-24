import asyncio
import time
import uuid
from typing import Dict, Any


class MockFallbackProvider:
    name = "mock-fallback"

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.perf_counter()

        # fast + reliable fallback (no timeout wrapper)
        await asyncio.sleep(0.05)

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
            "model": payload.get("model", "fallback-model"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"Fallback response to: {user_content}",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }

        latency_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = latency_ms

        return result