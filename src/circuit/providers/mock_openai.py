from __future__ import annotations
import time

class MockOpenAIProvider:
    async def chat_completions(self, payload: dict):
        content = payload["messages"][-1]["content"]

        # simulate failure trigger
        if "fail" in content or "force failure" in content:
            raise Exception("forced failure")

        return {
            "id": f"mock-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "gpt-4o",  
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Mock response",
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