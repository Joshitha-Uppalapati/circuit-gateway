import time
import uuid
from typing import Dict, Any


class MockOpenAIProvider:
    name = "mock-openai"

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()

        messages = payload.get("messages", [])
        user_content = ""

        for m in reversed(messages):
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break

        created = int(time.time())
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        time.sleep(0.01)

        latency_ms = int((time.time() - start) * 1000)

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
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
            "latency_ms": latency_ms,
        }

    async def chat_completions_stream(self, payload):
        yield 'data: {"choices":[{"delta":{"content":"Mock "}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"stream "}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"response"}}]}\n\n'
        yield "data: [DONE]\n\n"