import httpx
import time
from typing import Dict, Any


class OllamaProvider:
    name = "ollama"

    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.perf_counter()

        messages = payload.get("messages", [])
        user_content = ""

        for m in reversed(messages):
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break

        try:
            timeout = httpx.Timeout(
                15.0,
                connect=2.0,
                read=15.0,
                write=5.0,
                pool=5.0,
            )

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "http://127.0.0.1:11434/api/generate",
                    json={
                        "model": "llama3.2:1b",
                        "prompt": user_content,
                        "stream": False,
                        "options": {
                            "num_predict": 20,
                            "temperature": 0.3,
                        },
                    },
                )

            if response.status_code != 200:
                return {
                    "error": {
                        "code": "ollama_error",
                        "message": f"Ollama HTTP {response.status_code}: {response.text}",
                    }
                }

            data = response.json()

        except Exception as e:
            return {
                "error": {
                    "code": "ollama_connection_failed",
                    "message": str(e),
                }
            }

        latency_ms = int((time.perf_counter() - start) * 1000)

        return {
            "id": "ollama-fallback",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "llama3.2:1b",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": data.get("response", ""),
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