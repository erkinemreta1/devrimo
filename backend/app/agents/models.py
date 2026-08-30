"""Model construction shared by the legacy and Scholar profiles."""

from agno.models.base import Model

from app.config import get_settings


def build_model() -> Model:
    settings = get_settings()
    if settings.agent_runtime == "fake":
        from app.agents.echo_model import EchoModel

        return EchoModel()

    base_url = (settings.agent_openai_base_url or "").lower()
    if "opencode.ai" in base_url or settings.agent_model == "muse-spark-1.2-contributor":
        from agno.models.openai import OpenAIResponses

        return OpenAIResponses(
            id=settings.agent_model,
            api_key=settings.agent_openai_api_key,
            base_url=settings.agent_openai_base_url,
            max_output_tokens=settings.agent_max_tokens,
            reasoning_effort=settings.agent_reasoning_effort,
            verbosity=settings.agent_verbosity,
        )

    if "openrouter.ai" in base_url:
        from agno.models.openrouter import OpenRouter

        return OpenRouter(
            id=settings.agent_model,
            api_key=settings.agent_openai_api_key,
            base_url=settings.agent_openai_base_url,
            max_tokens=settings.agent_max_tokens,
        )

    from agno.models.openai import OpenAIChat

    return OpenAIChat(
        id=settings.agent_model,
        api_key=settings.agent_openai_api_key,
        base_url=settings.agent_openai_base_url,
        max_tokens=settings.agent_max_tokens,
    )
