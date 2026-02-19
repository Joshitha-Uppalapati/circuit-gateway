import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("circuit.request")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        request_id = getattr(request.state, "request_id", "-")
        logger.info(
            "%s %s %d %s %.2fms",
            request_id,
            request.method,
            response.status_code,
            request.url.path,
            duration_ms,
            )

        return response
