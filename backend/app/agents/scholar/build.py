"""Construct the production Scholar profile."""

from agno.agent import Agent
from agno.tools.mcp import MCPTools

from app.agents.models import build_model
from app.agents.scholar.hooks import production_tool_hook
from app.agents.scholar.learning import build_compression, build_learning
from app.agents.scholar.prompt import runtime_instructions
from app.agents.store import get_agno_db
from app.config import get_settings


def build_scholar_agent(connected: list[MCPTools]) -> Agent:
    settings = get_settings()
    model = build_model()
    compression = build_compression(model)
    return Agent(
        id="devrimo-scholar",
        name="Devrimo Scholar",
        description="A grounded, privacy-conscious ODTÜ student assistant.",
        model=model,
        db=get_agno_db(),
        tools=list(connected),
        tool_hooks=[production_tool_hook],
        tool_call_limit=settings.agent_tool_call_limit,
        instructions=runtime_instructions(connected),
        use_instruction_tags=True,
        add_history_to_context=True,
        num_history_runs=settings.scholar_history_runs,
        # Dependencies are rendered into the system instructions. Agno's
        # add_dependencies_to_context option appends them to—and persists them
        # inside—the user message, which corrupts history and leaks metadata to
        # the student-facing transcript.
        add_dependencies_to_context=False,
        resolve_in_context=True,
        add_datetime_to_context=True,
        timezone_identifier="Europe/Istanbul",
        datetime_format="%Y-%m-%d %H:%M (%A)",
        learning=build_learning(model),
        compress_tool_results=compression is not None,
        compression_manager=compression,
        offload_tool_results=False,
        store_tool_messages=False,
        store_events=settings.agent_store_events,
        checkpoint="runs",
        retries=settings.agent_retries,
        delay_between_retries=1,
        exponential_backoff=True,
        markdown=True,
        telemetry=False,
    )
