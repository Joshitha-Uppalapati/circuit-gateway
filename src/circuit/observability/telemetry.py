import os
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from circuit.config import settings


def setup_telemetry(app):
    if os.getenv("OTEL_ENABLED", "false").lower() != "true":
        return

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.OTEL_SERVICE_VERSION,
            "deployment.environment": settings.APP_ENV,
        }
    )

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    exporter = OTLPSpanExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
        or settings.OTEL_EXPORTER_OTLP_ENDPOINT
    )

    provider.add_span_processor(BatchSpanProcessor(exporter))

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


def get_tracer():
    return trace.get_tracer(__name__)