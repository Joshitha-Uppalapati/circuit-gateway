from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any


class ChatProvider(ABC):
    @abstractmethod
    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a chat request and return an OpenAI-compatible response. Raises on failure."""
        raise NotImplementedError

    async def chat_completions_stream(self, payload: Dict[str, Any]):
        raise NotImplementedError