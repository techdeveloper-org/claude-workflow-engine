"""OpenTelemetry distributed tracing for the Claude Workflow Engine pipeline.

Provides:
- init_tracing(): configure TracerProvider with OTLP gRPC or console exporter
- create_span(name, attributes): context manager yielding a live or no-op span
- get_trace_context(): extract current trace_id / span_id as strings

All functions degrade gracefully to no-ops when opentelemetry packages are not
installed, so callers never need to guard with try/except.

Usage::

    from langgraph_engine.tracing import init_tracing, create_span, get_trace_context

    init_tracing()  # call once at startup

    with create_span("step_5_skill_selection", {"session_id": sid}) as span:
        # span is a live OTEL span or _NoOpSpan
        result = select_skills(task)
        span.set_attribute("skill_count", len(result))

    ctx = get_trace_context()  # {"trace_id": "...", "span_id": "..."} or {}

Environment variables:
    ENABLE_TRACING                Set to "1" to activate tracing (default: off).
    OTEL_SERVICE_NAME             Service name sent to collector (default: "claude-workflow-engine").
    OTEL_EXPORTER_OTLP_ENDPOINT  gRPC endpoint, e.g. "http://otel-collector:4317".
                                  When unset, a console exporter is used instead.

ASCII-only: cp1252 safe (Windows).
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional opentelemetry imports
# ---------------------------------------------------------------------------
_HAS_OTEL = False
_tracer: Any = None

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _HAS_OTEL = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# No-op span / context manager for graceful degradation
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """Stand-in for an OTEL span when tracing is disabled or unavailable."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        pass

    def record_exception(self, exc: BaseException) -> None:  # noqa: D401
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        pass

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


_NOOP_SPAN = _NoOpSpan()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_tracing_initialized = False


def init_tracing(service_name: Optional[str] = None) -> bool:
    """Configure the global TracerProvider.

    Safe to call multiple times; subsequent calls are no-ops.

    Args:
        service_name: Override OTEL_SERVICE_NAME env var.

    Returns:
        True if tracing was successfully initialised, False otherwise.
    """
    global _tracing_initialized, _tracer

    if _tracing_initialized:
        return True

    if os.environ.get("ENABLE_TRACING", "0") != "1":
        return False

    if not _HAS_OTEL:
        logger.warning(
            "opentelemetry packages not installed; tracing disabled. "
            "Install: opentelemetry-sdk opentelemetry-exporter-otlp"
        )
        return False

    try:
        name = service_name or os.environ.get("OTEL_SERVICE_NAME", "claude-workflow-engine")
        resource = Resource.create({"service.name": name})
        provider = TracerProvider(resource=resource)

        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

                exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
                logger.info("OTEL: using OTLP gRPC exporter -> %s", otlp_endpoint)
            except ImportError:
                logger.warning("opentelemetry-exporter-otlp not installed; falling back to console exporter")
                exporter = ConsoleSpanExporter()
        else:
            exporter = ConsoleSpanExporter()
            logger.info("OTEL: using console span exporter (set OTEL_EXPORTER_OTLP_ENDPOINT for remote)")

        provider.add_span_processor(BatchSpanProcessor(exporter))
        _otel_trace.set_tracer_provider(provider)
        _tracer = _otel_trace.get_tracer(name)
        _tracing_initialized = True
        logger.info("OpenTelemetry tracing initialised for service '%s'", name)
        return True

    except Exception as exc:
        logger.warning("Failed to initialise tracing: %s", exc)
        return False


@contextmanager
def create_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """Context manager that yields a live OTEL span or a no-op span.

    Args:
        name:       Span name (e.g. "step_5_skill_selection").
        attributes: Key/value pairs attached to the span at creation time.

    Yields:
        A live opentelemetry.trace.Span or _NoOpSpan.
    """
    if not (_tracing_initialized and _HAS_OTEL and _tracer is not None):
        yield _NOOP_SPAN
        return

    try:
        with _tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    try:
                        span.set_attribute(key, value)
                    except Exception:
                        pass
            yield span
    except Exception as exc:
        logger.debug("Span '%s' raised: %s", name, exc)
        yield _NOOP_SPAN


def get_trace_context() -> Dict[str, str]:
    """Return the current trace_id and span_id as hex strings.

    Returns:
        Dict with keys "trace_id" and "span_id", or an empty dict when tracing
        is disabled or no active span exists.
    """
    if not (_tracing_initialized and _HAS_OTEL):
        return {}

    try:
        span = _otel_trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid:
            return {}
        return {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
        }
    except Exception:
        return {}
