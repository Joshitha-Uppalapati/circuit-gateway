from abc import ABC, abstractmethod
from typing import Dict, Any


class ChatProvider(ABC):
    @abstractmethod
    async def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a chat completion request against the provider.
        Returns an OpenAI-compatible response dict.
        """
        raise NotImplementedError
    
    async def chat_completions_stream(self, payload):
        raise NotImplementedError