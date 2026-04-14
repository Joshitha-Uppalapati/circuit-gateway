import os

from fastapi import FastAPI

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_tracer = trace.get_tracer("circuit")


def setup_telemetry(app: FastAPI):
    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "circuit-gateway"),
            "service.version": os.getenv("OTEL_SERVICE_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("APP_ENV", "dev"),
        }
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=os.getenv(
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                    os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"),
                )
            )
        )
    )

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


def get_tracer():
    return _tracer