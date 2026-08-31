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

*Never leak a secret.* ``before_send`` is the last gate every SDK event passes
through, and it scrubs credential-shaped values regardless of which call site
produced them. Prompt, completion, and tool content is deliberately allowed
through; keys, tokens, and passwords are not.
"""

from __future__ import annotations

import math
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
_SECRET_VALUE_PATTERN = re.compile(
    r"((?:Bearer|Basic)\s+[\w\-.=]+|eyJ[\w\-]{8,}\.[\w\-]{8,}\.[\w\-]+|ph[cx]_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9_-]{16,})"
)
_SAFE_AI_METRIC_KEY_PATTERN = re.compile(
    r"^\$ai_(?:input|output|total|cache_read|cache_creation|reasoning|web_search).*tokens$"
    r"|^\$ai_(?:input|output)_token_price$"
)
_REDACTED = "[redacted]"


def _non_negative_number(properties: dict[str, Any], key: str) -> float | None:
    """Return a finite, non-negative numeric PostHog property."""
    try:
        value = float(properties[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _add_ai_cost_properties(event: Any) -> None:
    """Add explicit USD costs to generation events using configured prices.

    PostHog's OpenAI wrapper records token counts, but the broker uses a
    custom OpenAI-compatible provider whose model is not in PostHog's price
    table. The wrapper also carries our per-token prices, so this final event
    hook can emit stable cost properties after the response usage is known.
    """
    if not isinstance(event, dict) or event.get("event") != "$ai_generation":
        return
    properties = event.get("properties")
    if not isinstance(properties, dict):
        return

    costs: list[float] = []
    for tokens_key, price_key, cost_key in (
        ("$ai_input_tokens", "$ai_input_token_price", "$ai_input_cost_usd"),
        ("$ai_output_tokens", "$ai_output_token_price", "$ai_output_cost_usd"),
    ):
        tokens = _non_negative_number(properties, tokens_key)
        price = _non_negative_number(properties, price_key)
        if tokens is None or price is None:
            continue
        cost = round(tokens * price, 12)
        properties.setdefault(cost_key, cost)
        costs.append(cost)

    if costs:
        properties.setdefault("$ai_total_cost_usd", round(sum(costs), 12))


def _scrub(value: Any, depth: int = 0) -> Any:
    """Recursively redact credential-shaped keys and values."""
    # Event payloads are JSON-shaped and therefore acyclic by the time the SDK
    # accepts them. A generous ceiling avoids pathological recursion without
    # ever returning an uninspected deep value that could contain a credential.
    if depth > 20:
        return _REDACTED
    if isinstance(value, dict):
        return {
            key: (
                _REDACTED
                if isinstance(key, str)
                and _SECRET_KEY_PATTERN.search(key)
                and not _SAFE_AI_METRIC_KEY_PATTERN.search(key)
                else _scrub(item, depth + 1)
            )
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
        # posthog-python's before_send contract is a mutable event dictionary,
        # not an object with a ``properties`` attribute. Keep the small object
        # fallback for duck-typed callers, but exercise the real dictionary
        # shape in tests so SDK events cannot bypass redaction unnoticed.
        properties = event.get("properties") if isinstance(event, dict) else getattr(event, "properties", None)
        if isinstance(properties, dict):
            scrubbed = _scrub(properties)
            if isinstance(event, dict):
                event["properties"] = scrubbed
            else:
                event.properties = scrubbed
            _add_ai_cost_properties(event)
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
        # Full AI capture is deliberate: prompts, completions, and tool state
        # are the evidence needed to debug a turn. ``before_send`` still strips
        # credential-shaped keys and values from every SDK event.
        privacy_mode=False,
        enable_full_ai_capture=True,
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
