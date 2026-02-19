import time
import uuid
from typing import Dict, Any


class MockOpenAIProvider:
    name = "mock-openai"

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        messages = payload.get("messages", [])
        user_content = ""

        for m in reversed(messages):
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break

        created = int(time.time())
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        return {"error": {"message": "simulated failure"}}
        
    async def chat_completions_stream(self, payload):
        yield 'data: {"choices":[{"delta":{"content":"Mock "}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"stream "}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"response"}}]}\n\n'
        yield "data: [DONE]\n\n"