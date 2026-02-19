from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# Request models
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    stream: bool | None = False
    model: str
    messages: List[ChatMessage]

    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    stop: Optional[List[str]] = None

    user: Optional[str] = None

# Response models
class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str

    choices: List[ChatCompletionChoice]
    usage: Optional[UsageInfo] = None


# Internal normalized model
class NormalizedChatResponse(BaseModel):
    """
    Provider-agnostic response format used internally.
    """

    text: str
    model: str
    provider: str

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    raw: Dict[str, Any]