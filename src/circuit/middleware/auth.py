from __future__ import annotations

import hashlib
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from circuit.config import settings


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get("authorization") or ""
        token = raw.replace("Bearer", "").strip()

        if not token:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "authentication_error", "message": "Missing API key"}},
            )

        if token not in settings.api_keys:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "authentication_error", "message": "Invalid API key"}},
            )

        request.state.client_key_hash = hashlib.sha256(token.encode()).hexdigest()[:12]
        return await call_next(request)