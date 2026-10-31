import logging
import os
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from opentelemetry.sdk.resources import Resource

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

from opentelemetry import _logs
from opentelemetry.sdk._logs import (
    LoggerProvider,
)
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import AsyncEngine

from urllib.parse import urljoin

from people_gator_api.settings import settings

P = ParamSpec("P")
R = TypeVar("R")


def trace(
    name: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Create a decorator that wraps an async function call in an OpenTelemetry span."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        span_name = name or f"{func.__module__}.{func.__qualname__}"
        tracer = otel_trace.get_tracer(func.__module__)

        @wraps(func)
        async def wrapped_async(*args: P.args, **kwargs: P.kwargs) -> R:
            with tracer.start_as_current_span(span_name):
                return await func(*args, **kwargs)

        return wrapped_async

    return decorator


def telemetry_resource() -> Resource:
    return Resource.create(
        {
            "service.name": "people-gator-api",
            "service.version": settings.deployment.version,
            "deployment.environment.name": settings.deployment.environment,
            "vcs.ref.head.revision": settings.deployment.commit,
            "people-gator.preview.pr": settings.deployment.pr_number,
            "service.instance.id": os.uname().nodename,
        }
    )

def signal_endpoint(signal: str) -> str:
    # Preserve an OpenObserve organization prefix and standard signal overrides.
    return os.getenv(f"OTEL_EXPORTER_OTLP_{signal.upper()}_ENDPOINT") or urljoin(
        settings.otel.http_endpoint.rstrip("/") + "/",
        getattr(settings.otel, f"{signal}_path").lstrip("/"),
    )


def initialize_opentelemetry():
    resource = telemetry_resource()
    trace_exporter = OTLPSpanExporter(
        endpoint=signal_endpoint("traces")
    )
    trace_processor = BatchSpanProcessor(trace_exporter)
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(trace_processor)
    otel_trace.set_tracer_provider(trace_provider)

    meter_exporter = OTLPMetricExporter(
        endpoint=signal_endpoint("metrics")
    )
    meter_reader = PeriodicExportingMetricReader(meter_exporter)
    meter_provider = MeterProvider([meter_reader], resource=resource)
    metrics.set_meter_provider(meter_provider)

    log_exporter = OTLPLogExporter(
        endpoint=signal_endpoint("logs")
    )
    log_processor = BatchLogRecordProcessor(log_exporter)
    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(log_processor)
    _logs.set_logger_provider(log_provider)

    logging_instrumentator = LoggingInstrumentor(log_level=logging.DEBUG)
    system_metric_instrumentator = SystemMetricsInstrumentor()
    fastapi_instrumentor = FastAPIInstrumentor()
    aiohttp_client_instrumentor = AioHttpClientInstrumentor()
    asyncpg_instrumentor = AsyncPGInstrumentor()
    weaviate_instrumentor = WeaviateInstrumentor()
    logging_instrumentator.instrument(set_logging_format=True)
    system_metric_instrumentator.instrument()
    aiohttp_client_instrumentor.instrument()
    # This captures driver-level operations such as connection acquisition and
    # prepared statement execution. SQLAlchemy spans are attached per engine
    # below so calls made through the ORM retain both layers of context.
    asyncpg_instrumentor.instrument()
    weaviate_instrumentor.instrument()

    return (
        fastapi_instrumentor,
        aiohttp_client_instrumentor,
        weaviate_instrumentor,
    )


def instrument_sqlalchemy_engine(engine: AsyncEngine) -> None:
    """Attach SQL query spans to an already-created async SQLAlchemy engine."""
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
