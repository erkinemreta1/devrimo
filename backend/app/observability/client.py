"""The single PostHog client for the broker, and safe wrappers around it.

Three rules shape this module.

*Never break the broker.* PostHog is optional. With no ``POSTHOG_API_KEY`` the
client is ``None`` and every helper below is a no-op, so a developer without a
PostHog project — and CI, which has none — runs an unmodified service. Nothing
in here is allowed to raise into a caller: an analytics sink that can fail a
chat turn is worse than no analytics sink.

*Never fail silently.* The corollary of the rule above is that a
mis-configuration looks exactly like a working install. So in debug builds the
absence of a key is announced once, loudly, at startup.

*Never leak a secret.* ``before_send`` is the last gate every event passes
through, and it scrubs credential-shaped values regardless of which call site
produced them. Prompt and completion content is deliberately allowed through
(see ``POSTHOG_CAPTURE_CONTENT``); keys, tokens and passwords are not.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from posthog import Posthog

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

MISSING_KEY_MESSAGE = (
    "POSTHOG_API_KEY variable required by PostHog is missing or un-configured, "
    "this causes events to be silently missed. This error stops appearing once "
    "POSTHOG_API_KEY is configured"
)

# Property names whose values are redacted no matter where they came from.
_SECRET_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api_?key|authorization|cookie|credential|jwt|bearer)",
    re.IGNORECASE,
)
# Value shapes that are credentials wherever they appear: bearer headers, JWTs,
# and PostHog's own personal API keys.
_SECRET_VALUE_PATTERN = re.compile(r"(Bearer\s+[\w\-.=]+|eyJ[\w\-]{8,}\.[\w\-]{8,}\.[\w\-]+|phx_[A-Za-z0-9]{16,})")
_REDACTED = "[redacted]"


def _scrub(value: Any, depth: int = 0) -> Any:
    """Recursively redact credential-shaped keys and values."""
    if depth > 6:
        return value
    if isinstance(value, dict):
        return {
            key: (_REDACTED if isinstance(key, str) and _SECRET_KEY_PATTERN.search(key) else _scrub(item, depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(item, depth + 1) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE_PATTERN.sub(_REDACTED, value)
    return value


def _before_send(event: Any) -> Any:
    """Last gate before upload. Must never raise — a throw here drops the queue."""
    try:
        properties = getattr(event, "properties", None)
        if isinstance(properties, dict):
            event.properties = _scrub(properties)
    except Exception:  # pragma: no cover - defensive; scrubbing must not break capture
        return event
    return event


@lru_cache
def get_posthog() -> Posthog | None:
    """The process-wide PostHog client, or ``None`` when unconfigured."""
    settings = get_settings()

    if not settings.posthog_configured:
        if settings.posthog_debug:
            logger.error("posthog_not_configured", detail=MISSING_KEY_MESSAGE)
        return None

    client = Posthog(
        settings.posthog_api_key,
        host=settings.posthog_host,
        debug=settings.posthog_debug,
        # Local evaluation keeps feature-flag checks off the network on the
        # chat hot path. Without a personal key the SDK falls back to the
        # decide endpoint, which still works, just slower.
        personal_api_key=settings.posthog_personal_api_key or None,
        enable_local_evaluation=bool(settings.posthog_personal_api_key),
        super_properties={
            "service": "devrimo-broker",
            "agent_profile": settings.agent_profile,
            "agent_runtime": settings.agent_runtime,
            "agent_model": settings.agent_model,
        },
        # Unhandled exceptions anywhere in the process become issues. Rate
        # limited so a hot loop of failures cannot flood the queue.
        enable_exception_autocapture=True,
        enable_exception_autocapture_rate_limiting=True,
        log_captured_exceptions=True,
        # Local variables at the point of the throw, with secret detection on.
        # This is the difference between "MCPError" and knowing which server,
        # which argument, and which student hit it.
        capture_exception_code_variables=True,
        code_variables_detect_secrets=True,
        code_variables_mask_url_credentials=True,
        code_variables_mask_patterns=[
            "password",
            "metu_password",
            "secret",
            "token",
            "api_key",
            "access_token",
            "authorization",
        ],
        project_root="/app",
        in_app_modules=["app"],
        # `privacy_mode` strips $ai_input/$ai_output_choices everywhere; full
        # capture additionally disables PostHog's own string truncation so long
        # transcripts and tool results arrive whole.
        privacy_mode=not settings.posthog_capture_content,
        enable_full_ai_capture=settings.posthog_capture_content,
        capture_trace_context=True,
        before_send=_before_send,
    )
    logger.info("posthog_initialized", host=settings.posthog_host)
    return client


def capture(event: str, *, distinct_id: str | None = None, **properties: Any) -> None:
    """Capture an event, inheriting distinct id and session from the request context."""
    client = get_posthog()
    if client is None:
        return
    try:
        if distinct_id is None:
            client.capture(event, properties=properties)
        else:
            client.capture(event, distinct_id=distinct_id, properties=properties)
    except Exception as exc:  # pragma: no cover - telemetry must never break a request
        logger.warning("posthog_capture_failed", event=event, error=exc.__class__.__name__)


def capture_exception(exc: BaseException, *, distinct_id: str | None = None, **properties: Any) -> None:
    """Report a handled exception that would otherwise never reach autocapture."""
    client = get_posthog()
    if client is None:
        return
    try:
        if distinct_id is None:
            client.capture_exception(exc, properties=properties)
        else:
            client.capture_exception(exc, distinct_id=distinct_id, properties=properties)
    except Exception as capture_error:  # pragma: no cover
        logger.warning("posthog_capture_exception_failed", error=capture_error.__class__.__name__)


def shutdown() -> None:
    """Flush the queue. Called from the app lifespan; an unflushed queue at
    SIGTERM loses exactly the events explaining why the process is going away."""
    client = get_posthog()
    if client is None:
        return
    try:
        client.shutdown()
    except Exception as exc:  # pragma: no cover
        logger.warning("posthog_shutdown_failed", error=exc.__class__.__name__)
