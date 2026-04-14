from __future__ import annotations

import tiktoken
from functools import lru_cache


@lru_cache(maxsize=8)
def _get_encoding(model: str):
   
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens_from_messages(model: str, messages: list[dict]) -> int:
    encoding = _get_encoding(model)

    tokens = 0

    for message in messages:
        tokens += 4  # role + formatting overhead
        for key, value in message.items():
            tokens += len(encoding.encode(str(value)))

    tokens += 2  # assistant priming

    return tokens


def count_tokens_from_text(model: str, text: str) -> int:
    encoding = _get_encoding(model)
    return len(encoding.encode(text))

def truncate_text_to_max_tokens(model: str, text: str, max_tokens: int) -> str:
    try:
        import tiktoken

        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")

    token_ids = encoding.encode(text)
    if len(token_ids) <= max_tokens:
        return text

    return encoding.decode(token_ids[:max_tokens])

