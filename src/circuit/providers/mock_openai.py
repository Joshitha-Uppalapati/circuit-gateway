import asyncio
import time
import uuid
from typing import Dict, Any

from circuit.reliability.timeouts import DEFAULT_TIMEOUT


class MockOpenAIProvider:
    name = "mock-openai"

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.perf_counter()

        async def _simulate():
            # simulate slow upstream → triggers timeout
            await asyncio.sleep(2)

            messages = payload.get("messages", [])
            user_content = ""

            for m in reversed(messages):
                if m.get("role") == "user":
                    user_content = m.get("content", "")
                    break

            return {
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
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }

        try:
            result = await asyncio.wait_for(
                _simulate(),
                timeout=DEFAULT_TIMEOUT.total_timeout,
            )
        except asyncio.TimeoutError:
            return {
                "error": {
                    "code": "timeout",
                    "message": "Provider request timed out",
                }
            }

        latency_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = latency_ms

        return result