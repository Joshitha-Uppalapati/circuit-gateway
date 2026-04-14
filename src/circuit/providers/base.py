from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any


class ChatProvider(ABC):
    @abstractmethod
    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def chat_completions_stream(self, payload: Dict[str, Any]):
        pass