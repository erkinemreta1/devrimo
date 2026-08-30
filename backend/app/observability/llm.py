"""AI observability: one PostHog trace per chat turn, every generation inside it.

Agno owns the model loop, so there is no single place in this codebase where a
turn's LLM calls are visible — one turn can be a first completion, N tool
round-trips, a compression pass and a learning pass, each a separate request to
the provider. Instrumenting the two ``arun``/``acontinue_run`` call sites in the
chat route would therefore miss most of them.

Instead the *client* is instrumented. ``app.agents.models.build_model`` is the
only place a model client is constructed, Agno's ``OpenAIChat``/``OpenAIResponses``
accept an injected ``async_client``, and PostHog's ``AsyncOpenAI`` is a genuine
subclass of ``openai.AsyncOpenAI`` — so swapping it in captures every generation
in the process, including the ones Agno makes on its own initiative.

Two things the stock wrapper cannot know are supplied here from contextvars set
by the chat route:

``$ai_trace_id``
    PostHog mints a fresh UUID per call when none is passed, which would shatter
    one turn into a dozen unrelated single-generation traces. The trace id is
    the turn.

``$ai_session_id``
    The chat session the student sees in their sidebar, so a whole conversation
    can be read as one thing.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

# Set per turn by the chat route; read by every nested model call.
current_trace_id: ContextVar[str | None] = ContextVar("posthog_ai_trace_id", default=None)
current_session_id: ContextVar[str | None] = ContextVar("posthog_ai_session_id", default=None)


def new_trace_id() -> str:
    return str(uuid4())


@contextmanager
def llm_turn(trace_id: str, session_id: str | None = None) -> Iterator[str]:
    """Scope every LLM call made inside to one PostHog trace."""
    trace_token = current_trace_id.set(trace_id)
    session_token = current_session_id.set(session_id)
    try:
        yield trace_id
    finally:
        current_trace_id.reset(trace_token)
        current_session_id.reset(session_token)


def trace_properties() -> dict[str, Any]:
    """Properties every AI event in the current turn should carry."""
    properties: dict[str, Any] = {}
    session_id = current_session_id.get()
    if session_id:
        properties["$ai_session_id"] = session_id
    return properties


def _cost_properties() -> dict[str, Any]:
    """Per-token prices for a model PostHog has no price table for.

    The broker talks to an OpenAI-compatible endpoint serving
    ``muse-spark-1.2-contributor``. Without these, every generation reports a
    cost of zero and per-student cost analysis is silently meaningless.
    """
    settings = get_settings()
    properties: dict[str, Any] = {}
    if settings.posthog_input_token_price:
        properties["$ai_input_token_price"] = settings.posthog_input_token_price
    if settings.posthog_output_token_price:
        properties["$ai_output_token_price"] = settings.posthog_output_token_price
    return properties


def _defaults(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Fill in the PostHog arguments Agno has no way to pass."""
    settings = get_settings()

    if kwargs.get("posthog_trace_id") is None:
        trace_id = current_trace_id.get()
        if trace_id is not None:
            kwargs["posthog_trace_id"] = trace_id

    merged = {**trace_properties(), **_cost_properties()}
    if merged:
        # An explicit caller value always wins over the ambient one.
        kwargs["posthog_properties"] = {**merged, **(kwargs.get("posthog_properties") or {})}

    if not kwargs.get("posthog_privacy_mode"):
        kwargs["posthog_privacy_mode"] = not settings.posthog_capture_content

    if kwargs.get("posthog_provider_override") is None:
        # Reported as $ai_provider so cost attribution does not claim these
        # were OpenAI calls. The wrapper still parses OpenAI-shaped responses.
        kwargs["posthog_provider_override"] = _provider_name(settings.agent_openai_base_url)

    return kwargs


def _provider_name(base_url: str) -> str:
    if "opencode.ai" in base_url:
        return "opencode"
    if "openrouter.ai" in base_url:
        return "openrouter"
    return "openai"


def build_traced_async_client(**client_kwargs: Any):
    """A PostHog-instrumented ``AsyncOpenAI`` that inherits the ambient trace.

    Returns ``None`` when PostHog is unconfigured, so ``build_model`` falls back
    to the stock Agno client and nothing about the agent changes.
    """
    from app.observability.client import get_posthog

    posthog_client = get_posthog()
    if posthog_client is None:
        return None

    try:
        from posthog.ai.openai.openai_async import (
            AsyncOpenAI as PostHogAsyncOpenAI,
        )
        from posthog.ai.openai.openai_async import (
            WrappedChat,
            WrappedCompletions,
            WrappedResponses,
        )
    except Exception as exc:  # pragma: no cover - posthog[otel] not installed
        logger.warning("posthog_ai_wrapper_unavailable", error=exc.__class__.__name__)
        return None

    class _TracedCompletions(WrappedCompletions):
        async def create(self, **kwargs: Any):
            return await super().create(**_defaults(kwargs))

        async def parse(self, **kwargs: Any):
            return await super().parse(**_defaults(kwargs))

    class _TracedChat(WrappedChat):
        @property
        def completions(self):
            # `WrappedChat.completions` is a property that builds a fresh
            # wrapper per access, so this override — not an attribute
            # assignment — is what makes the tracing stick.
            return _TracedCompletions(self._client, self._original.completions)

    class _TracedResponses(WrappedResponses):
        async def create(self, **kwargs: Any):
            return await super().create(**_defaults(kwargs))

    class _TracedAsyncOpenAI(PostHogAsyncOpenAI):
        def __init__(self, **kwargs: Any):
            super().__init__(posthog_client=posthog_client, **kwargs)
            # Re-wrap the two resources Agno actually calls with the traced
            # subclasses. `_original_*` is set by PostHog's own wrapping pass.
            self.chat = _TracedChat(self, self._original_chat)
            self.responses = _TracedResponses(self, self._original_responses)

    try:
        return _TracedAsyncOpenAI(**client_kwargs)
    except Exception as exc:
        # A model client that cannot be built must not take the agent down with
        # it; the caller falls back to the uninstrumented client.
        logger.warning("posthog_ai_client_build_failed", error=exc.__class__.__name__)
        return None
