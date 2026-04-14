import asyncio
import time


class MockOpenAIProvider:
    async def chat_completions(self, payload: dict):
        content = payload["messages"][0]["content"]

        # simulate latency spike
        if "slow" in content:
            await asyncio.sleep(2)  # triggers timeout

        # simulate failure
        if "fail" in content:
            raise Exception("simulated provider failure")

        # normal case
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