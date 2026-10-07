"""Configuración de OpenTelemetry compartida por service-a y service-b.

Emite los tres pilares de observabilidad:
  * Trazas  -> OTLP/gRPC -> OTel Collector -> Jaeger / X-Ray
  * Métricas -> OTLP/gRPC -> OTel Collector -> endpoint Prometheus (:8889)
  * Logs    -> JSON estructurado en stdout (con trace_id/span_id)
               + OTLP -> OTel Collector -> Loki / Cloud Logging / CloudWatch

Toda la configuración de destino se toma de las variables de entorno estándar
de OTel (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_RESOURCE_ATTRIBUTES, ...).

Con OTEL_SDK_DISABLED=true no se crea ningún provider ni se aplica
auto-instrumentación: es el modo "baseline" usado en el benchmark de overhead.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from datetime import datetime, timezone

from opentelemetry import metrics, trace

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "unknown-service")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")

# Atributos estándar de LogRecord; todo lo demás que llegue por `extra=` se serializa.
_RESERVED_LOG_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}
_OTEL_LOG_ATTRS = {"otelSpanID", "otelTraceID", "otelTraceSampled", "otelServiceName"}


# FastAPI >= 0.140 trae telemetría OTel nativa que se activa sola al detectar providers
# globales. Se desactiva: la instrumentación la hace FastAPIInstrumentor (contrib),
# y así se evita una capa ASGI extra por request y el intento de auto-configuración.
FASTAPI_NATIVE_TELEMETRY_OFF = {"tracing": False, "metrics": False, "logs": False, "auto_configure": False}


def otel_enabled() -> bool:
    return os.getenv("OTEL_SDK_DISABLED", "false").strip().lower() != "true"


def _signal_enabled(signal: str) -> bool:
    """Respeta OTEL_{TRACES,METRICS,LOGS}_EXPORTER=none (se usa en el análisis por componente)."""
    return os.getenv(f"OTEL_{signal}_EXPORTER", "otlp").strip().lower() != "none"


class JsonFormatter(logging.Formatter):
    """Logs estructurados en JSON con trace_id/span_id del span activo.

    El trace_id es el pivot de correlación: el mismo valor aparece en Jaeger,
    en los logs OTLP (Loki / Cloud Logging / CloudWatch) y en cada línea de stdout.
    """

    def format(self, record: logging.LogRecord) -> str:
        ctx = trace.get_current_span().get_span_context()
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service.name": SERVICE_NAME,
            "trace_id": format(ctx.trace_id, "032x") if ctx.is_valid else None,
            "span_id": format(ctx.span_id, "016x") if ctx.is_valid else None,
            "trace_flags": f"{int(ctx.trace_flags):02x}" if ctx.is_valid else None,
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_ATTRS and key not in _OTEL_LOG_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _configure_stdout_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    # El access log de uvicorn se desactiva: los spans HTTP ya registran cada request.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)


def setup_telemetry() -> None:
    """Inicializa providers globales de trazas, métricas y logs.

    Debe llamarse una sola vez al arrancar el proceso, antes de crear la app.
    """
    _configure_stdout_logging()
    log = logging.getLogger(__name__)

    if not otel_enabled():
        log.info("OpenTelemetry deshabilitado (modo baseline)")
        return

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    # Resource: identidad del servicio. OTEL_RESOURCE_ATTRIBUTES se fusiona automáticamente.
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": SERVICE_VERSION,
            "service.namespace": "otel-lab",
        }
    )

    # Una señal sin provider usa la implementación no-op de la API (costo ~0).

    # --- Trazas ---
    if _signal_enabled("TRACES"):
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

    # --- Métricas ---
    if _signal_enabled("METRICS"):
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(),
            export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "10000")),
        )
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    # --- Logs (OTLP) --- el LoggingHandler adjunta trace_id/span_id al LogRecord OTLP.
    if _signal_enabled("LOGS"):
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        set_logger_provider(logger_provider)
        logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))

    # Propagación W3C TraceContext (traceparent/tracestate) + Baggage entre servicios.
    set_global_textmap(CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()]))

    # CPU / memoria del proceso para el panel de CPU de Grafana.
    if _signal_enabled("METRICS"):
        SystemMetricsInstrumentor(
            config={
                "process.cpu.time": ["user", "system"],
                "process.cpu.utilization": ["user", "system"],
                "process.memory.usage": None,
                "process.thread.count": None,
            }
        ).instrument()

    log.info("OpenTelemetry inicializado", extra={"otlp_endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")})


def instrument_fastapi(app) -> None:
    """Auto-instrumentación HTTP server (spans + métricas http.server.*)."""
    if not otel_enabled():
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,health/ready")


def instrument_sqlalchemy(engine) -> None:
    """Auto-instrumentación de base de datos (un span por query, métricas de pool)."""
    if not otel_enabled():
        return
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine)


def instrument_httpx_client(client) -> None:
    """Auto-instrumentación HTTP client: crea span CLIENT e inyecta `traceparent`."""
    if not otel_enabled():
        return
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor.instrument_client(client)


def shutdown_telemetry() -> None:
    """Fuerza el flush de los exporters al apagar el proceso."""
    if not otel_enabled():
        return
    from opentelemetry._logs import get_logger_provider

    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider(), get_logger_provider()):
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            shutdown()


def untraced():
    """Contexto sin instrumentación: las sondas de salud de Kubernetes (cada ~10 s por pod)
    no deben generar trazas ni spans de base de datos que ensucien Jaeger / Cloud Trace."""
    if not otel_enabled():
        return contextlib.nullcontext()
    from opentelemetry.instrumentation.utils import suppress_instrumentation

    return suppress_instrumentation()


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None
