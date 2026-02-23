import time
from starlette.middleware.base import BaseHTTPMiddleware
from circuit.observability.metrics import metrics


class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        
        if request.url.path.startswith("/metrics") or request.url.path == "/health":
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        client = getattr(request.state, "client_key_hash", None)

        metrics.observe_latency(duration_ms, client=client)

        return response