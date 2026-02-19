from circuit.config import settings
from circuit.providers.base import ChatProvider
from circuit.providers.mock_openai import MockOpenAIProvider
from circuit.providers.openai import OpenAIProvider


def get_chat_provider() -> ChatProvider:
    provider = getattr(settings, "PROVIDER", "MOCK").upper()

    if provider == "OPENAI":
        return OpenAIProvider()

    return MockOpenAIProvider()