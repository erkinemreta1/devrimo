"""Per-request observability context.

Everything downstream — PostHog events, captured exceptions, structlog lines,
and the AI generations Agno makes inside the request — reads its identity from
here rather than passing a user id down through every call signature. Both
mechanisms are contextvar-based, so an ``await`` chain and Agno's own nested
model calls inherit it for free.

The distinct id is taken from the *verified* JWT and never from a request
header. ``X-POSTHOG-DISTINCT-ID`` is accepted only to be ignored: honouring it
would let any caller attribute events, LLM traces and exceptions to any other
student. ``X-POSTHOG-SESSION-ID`` is different — it is not an identity claim,
just the browser's replay session, and it is what links a backend LLM trace to
the recording of the student who triggered it.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

# Paths that would otherwise emit a request event on every health probe.
_QUIET_PATHS = frozenset({"/health", "/api/v1/health"})


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key == name:
            decoded = value.decode("latin-1").strip()
            return decoded or None
    return None


def _user_from_bearer(scope: Scope):
    """Best-effort identity. Never raises: this is telemetry, not authorization.

    The route's own ``get_current_user`` dependency remains the only thing that
    decides whether a request is allowed to proceed.
    """
    authorization = _header(scope, b"authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        from app.auth.jwt import verify_access_token

        return verify_access_token(authorization[7:].strip())
    except Exception:
        return None


class ObservabilityMiddleware:
    """Bind request identity into PostHog contexts and structlog contextvars."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        request_id = _header(scope, b"x-request-id") or str(uuid4())
        session_id = _header(scope, b"x-posthog-session-id")
        authenticated_user = _user_from_bearer(scope)
        user_id = str(authenticated_user.id) if authenticated_user else None
        if authenticated_user is not None:
            # Starlette exposes this same mapping as request.state. The route
            # dependency reuses the verified token instead of doing the same
            # signature/JWKS work a second time.
            scope.setdefault("state", {})["authenticated_user"] = authenticated_user
        path = scope.get("path", "")
        method = scope.get("method", "")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=path,
            method=method,
            **({"user_id": user_id} if user_id else {}),
            **({"session_id": session_id} if session_id else {}),
        )

        if not settings.posthog_configured:
            try:
                await self._call_with_status(scope, receive, send, request_id, path, method, user_id, capture=False)
            finally:
                structlog.contextvars.clear_contextvars()
            return

        from posthog import identify_context, new_context, set_context_session, tag

        # `capture_exceptions=True` turns anything that escapes a route into a
        # PostHog issue carrying every tag bound below.
        with new_context(capture_exceptions=True):
            if user_id:
                identify_context(user_id)
            if session_id:
                set_context_session(session_id)
            tag("request_id", request_id)
            tag("path", path)
            tag("method", method)
            tag("agent_profile", settings.agent_profile)
            tag("agent_runtime", settings.agent_runtime)
            try:
                await self._call_with_status(scope, receive, send, request_id, path, method, user_id, capture=True)
            finally:
                structlog.contextvars.clear_contextvars()

    async def _call_with_status(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        request_id: str,
        path: str,
        method: str,
        user_id: str | None,
        *,
        capture: bool,
    ) -> None:
        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                structlog.contextvars.bind_contextvars(status_code=status_code)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # 5xx responses that never raised — a route returning JSONResponse(500)
        # by hand, or the global handler having already converted the throw —
        # would otherwise leave no trace anywhere.
        if capture and status_code is not None and status_code >= 500 and path not in _QUIET_PATHS:
            from app.observability.client import capture as capture_event

            capture_event(
                "server_error_response",
                distinct_id=user_id,
                request_id=request_id,
                path=path,
                method=method,
                status_code=status_code,
            )
