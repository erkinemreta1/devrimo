"""Ship structlog output to PostHog Logs over OTLP.

There is a trap here worth naming. ``app.logging`` uses
``structlog.PrintLoggerFactory``, which writes straight to stdout and never
touches the stdlib ``logging`` module — so the usual advice, "attach an OTel
``LoggingHandler`` to the root logger", captures nothing in this service.

The forwarding therefore happens as a structlog *processor*. It emits each
event to an OTel logger and returns the event dict untouched, so stdout stays
byte-identical and container log collection is unaffected. Every existing
``logger.info/warning/error`` call site is covered without being edited, and
because ``merge_contextvars`` runs first in the chain, each record already
carries the request id, user id and session bound by ObservabilityMiddleware.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.observability.client import _scrub
from app.observability.llm import current_trace_id

# Structlog level names -> OTel severity. OTel wants both a number and a text.
_SEVERITY = {
    "critical": (21, "FATAL"),
    "exception": (17, "ERROR"),
    "error": (17, "ERROR"),
    "warning": (13, "WARN"),
    "warn": (13, "WARN"),
    "info": (9, "INFO"),
    "debug": (5, "DEBUG"),
    "notset": (0, "UNSPECIFIED"),
}

_logger_provider = None
_otel_logger = None
_failed = False


def _setup() -> Any:
    """Build the OTLP logger provider once. Returns ``None`` when unavailable."""
    global _logger_provider, _otel_logger, _failed
    if _otel_logger is not None or _failed:
        return _otel_logger

    settings = get_settings()
    if not settings.posthog_configured:
        _failed = True
        return None

    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource

        provider = LoggerProvider(
            resource=Resource.create(
                {
                    SERVICE_NAME: "devrimo-broker",
                    "service.version": settings.agent_profile,
                    "deployment.environment": settings.agent_runtime,
                }
            )
        )
        provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(
                    endpoint=f"{settings.posthog_host.rstrip('/')}/i/v1/logs",
                    headers={"Authorization": f"Bearer {settings.posthog_api_key}"},
                )
            )
        )
        set_logger_provider(provider)
        _logger_provider = provider
        _otel_logger = provider.get_logger("devrimo")
        return _otel_logger
    except Exception:
        # No OTLP exporter installed, or a bad host. Logging to stdout must
        # keep working regardless, so this is latched off rather than retried
        # on every single log line.
        _failed = True
        return None


def posthog_log_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor: forward, then hand the event on unchanged."""
    otel_logger = _setup()
    if otel_logger is None:
        return event_dict

    try:
        from opentelemetry._logs import SeverityNumber

        # OTLP bypasses the PostHog SDK and therefore its before_send hook.
        # Apply the same secret-only scrubber here while leaving the dictionary
        # returned to structlog untouched, so local stdout remains byte-identical.
        safe_event = _scrub(event_dict)
        if not isinstance(safe_event, dict):  # pragma: no cover - event_dict is typed as a dict
            return event_dict

        level = str(safe_event.get("level", "info")).lower()
        number, text = _SEVERITY.get(level, (9, "INFO"))

        attributes = {
            key: value
            for key, value in safe_event.items()
            if key not in ("event", "level", "timestamp") and isinstance(value, (str, int, float, bool))
        }
        # Links this log line to the AI trace it happened inside, so a failed
        # turn's logs are reachable from the trace and vice versa.
        trace_id = current_trace_id.get()
        if trace_id:
            attributes["$ai_trace_id"] = trace_id
        if "user_id" in safe_event:
            # PostHog links logs to a person through this property name.
            attributes["distinct_id"] = str(safe_event["user_id"])

        otel_logger.emit(
            body=str(safe_event.get("event", "")),
            severity_number=SeverityNumber(number),
            severity_text=text,
            attributes=attributes,
        )
    except Exception:  # pragma: no cover - a log sink must never break a log call
        pass
    return event_dict


def shutdown() -> None:
    """Flush buffered log records. Safe to call when never set up."""
    if _logger_provider is None:
        return
    try:
        _logger_provider.shutdown()
    except Exception:  # pragma: no cover
        pass


def stdlib_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.INFO)
