import logging
import sys
import time

from fastapi import Request
from pythonjsonlogger import jsonlogger
from starlette.middleware.base import BaseHTTPMiddleware

from opentelemetry import trace

from circuit.middleware.request_id import get_request_id

logger = logging.getLogger("circuit.request")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()

        span = trace.get_current_span()
        ctx = span.get_span_context()

        if ctx and ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = None
            record.span_id = None

        return True


def setup_logging():
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(trace_id)s %(span_id)s"
        )
    )

    root.setLevel(logging.INFO)
    root.addHandler(handler)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "request_complete",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "client_ip": request.client.host if request.client else None,
                "duration_ms": round(duration_ms, 2),
            },
        )

        return response