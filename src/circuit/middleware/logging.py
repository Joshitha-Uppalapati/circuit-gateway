import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from circuit.middleware.request_id import get_request_id

logger = logging.getLogger("circuit.request")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging():
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(request_id)s | %(name)s | %(message)s"
        )
    )
    root.setLevel(logging.INFO)
    root.addHandler(handler)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        logger.info(
            "%s %s %d %s %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            request.client.host if request.client else "-",
            duration_ms,
        )

        return response