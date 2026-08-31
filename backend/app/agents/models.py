"""Model construction shared by the legacy and Scholar profiles.

This is the only place in the broker where a model client is built, which makes
it the one place worth instrumenting: injecting a PostHog-wrapped
``AsyncOpenAI`` here captures every generation the process makes, including the
ones Agno initiates on its own — the tool loop's follow-up completions, the
Scholar learning pass, and tool-result compression — none of which are visible
from the chat route.
"""

from agno.models.base import Model

from app.agents.runtime import AgentRuntimeConfig, default_runtime_config
from app.config import get_settings
from app.logging import get_logger
from app.observability.flags import FLAG_AGENT_MODEL, flag_variant
from app.observability.llm import build_traced_async_client

logger = get_logger(__name__)


def _traced(model: Model) -> Model:
    """Swap in a PostHog-instrumented async client, if one can be built.

    Agno caches ``async_client`` and only rebuilds it when closed, so setting
    the field is enough. When PostHog is unconfigured this returns the model
    untouched and Agno constructs its own stock client as before — the agent
    behaves identically either way.
    """
    settings = get_settings()
    client_params = {
        "api_key": settings.agent_openai_api_key,
        "base_url": settings.agent_openai_base_url,
    }
    client = build_traced_async_client(**client_params)
    if client is None:
        return model
    model.async_client = client
    return model


def build_model(runtime: AgentRuntimeConfig | None = None) -> Model:
    settings = get_settings()
    runtime = runtime or default_runtime_config()
    if settings.agent_runtime == "fake":
        from app.agents.echo_model import EchoModel

        return EchoModel()

    # A flagged model override makes a model A/B measurable directly from the
    # $ai_generation events, and makes rolling back a bad model immediate.
    model_id = flag_variant(FLAG_AGENT_MODEL, default=runtime.model_id)

    base_url = (settings.agent_openai_base_url or "").lower()
    if "opencode.ai" in base_url or model_id == "muse-spark-1.2-contributor":
        from agno.models.openai import OpenAIResponses

        return _traced(
            OpenAIResponses(
                id=model_id,
                api_key=settings.agent_openai_api_key,
                base_url=settings.agent_openai_base_url,
                max_output_tokens=runtime.max_tokens,
            )
        )

    if "openrouter.ai" in base_url:
        from agno.models.openrouter import OpenRouter

        return _traced(
            OpenRouter(
                id=model_id,
                api_key=settings.agent_openai_api_key,
                base_url=settings.agent_openai_base_url,
                max_tokens=runtime.max_tokens,
            )
        )

    from agno.models.openai import OpenAIChat

    return _traced(
        OpenAIChat(
            id=model_id,
            api_key=settings.agent_openai_api_key,
            base_url=settings.agent_openai_base_url,
            max_tokens=runtime.max_tokens,
        )
    )
