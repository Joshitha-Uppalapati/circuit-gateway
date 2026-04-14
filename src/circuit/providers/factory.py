from circuit.config import settings
from circuit.providers.base import ChatProvider
from circuit.providers.mock_openai import MockOpenAIProvider
from circuit.providers.openai import OpenAIProvider

_provider: ChatProvider | None = None


def get_chat_provider() -> ChatProvider:
    global _provider

    if _provider is not None:
        return _provider

    provider_name = settings.PROVIDER.upper()

    if provider_name == "OPENAI":
        _provider = OpenAIProvider(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
    else:
        _provider = MockOpenAIProvider()

    return _provider


def get_active_providers():
    providers = []
    if _provider is not None:
        providers.append(_provider)
    return providers