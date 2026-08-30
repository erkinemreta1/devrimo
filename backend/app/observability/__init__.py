"""PostHog observability for the broker.

Import from here rather than from the submodules; the split is an
implementation detail.
"""

from app.observability.client import capture, capture_exception, get_posthog, shutdown
from app.observability.llm import (
    build_traced_async_client,
    current_session_id,
    current_trace_id,
    llm_turn,
    new_trace_id,
    trace_properties,
)
from app.observability.middleware import ObservabilityMiddleware

__all__ = [
    "ObservabilityMiddleware",
    "build_traced_async_client",
    "capture",
    "capture_exception",
    "current_session_id",
    "current_trace_id",
    "get_posthog",
    "llm_turn",
    "new_trace_id",
    "shutdown",
    "trace_properties",
]
