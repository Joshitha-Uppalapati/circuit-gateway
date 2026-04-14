import uuid
import contextvars

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

_request_id_ctx = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = _request_id_ctx.set(rid)
        request.state.request_id = rid
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)

        response.headers["X-Request-ID"] = rid
        return response