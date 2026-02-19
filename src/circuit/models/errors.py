from typing import Optional
from pydantic import BaseModel


class ProviderError(BaseModel):
    type: str
    message: str
    provider: str
    status_code: Optional[int] = None