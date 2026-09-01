"""Construct the production Scholar profile."""

from agno.agent import Agent
from agno.tools.mcp import MCPTools

from app.agents.models import build_model
from app.agents.runtime import AgentRuntimeConfig, default_runtime_config
from app.agents.scholar.hooks import production_tool_hook
from app.agents.scholar.learning import build_compression, build_learning
from app.agents.scholar.prompt import runtime_instructions
from app.agents.store import get_agno_db
from app.agents.tools.campus_fetch import read_campus_page
from app.agents.tools.compute import compute
from app.agents.tools.planning import make_plan_semester_tool
from app.config import get_settings
from app.knowledge.retrieval import build_retriever
from app.knowledge.store import knowledge_available
from app.observability.flags import (
    FLAG_CAMPUS_KNOWLEDGE,
    FLAG_HISTORY_RUNS,
    FLAG_TOOL_CALL_LIMIT,
    flag_enabled,
    int_payload,
)


def build_scholar_agent(connected: list[MCPTools], runtime: AgentRuntimeConfig | None = None) -> Agent:
    settings = get_settings()
    runtime = runtime or default_runtime_config()
    model = build_model(runtime)
    compression = build_compression(model)

    # The campus corpus is switchable three ways, and all three are ordinary
    # states: the deployment has no embeddings configured, an admin turned it
    # off, or a flag disabled it mid-incident because retrieval started serving
    # something wrong. In every case Scholar comes up with its campus MCP tools
    # and simply has no campus search.
    corpus_enabled = (
        runtime.knowledge_enabled and knowledge_available() and flag_enabled(FLAG_CAMPUS_KNOWLEDGE, default=True)
    )
    retriever = build_retriever() if corpus_enabled else None

    return Agent(
        id="devrimo-scholar",
        name="Devrimo Scholar",
        description="A grounded, privacy-conscious ODTÜ student assistant.",
        model=model,
        db=get_agno_db(),
        # Three general tools beside the campus servers, rather than one per
        # question the service is asked. `compute` is a restricted evaluator,
        # deliberately not Agno's PythonTools — see app/agents/tools/compute.py.
        tools=[*connected, compute, read_campus_page, make_plan_semester_tool(runtime.grade_policy)],
        tool_hooks=[production_tool_hook],
        # Tunable without a deploy: a model looping through tool calls is a
        # live incident, and this is the dial that stops it.
        tool_call_limit=int_payload(FLAG_TOOL_CALL_LIMIT, default=runtime.tool_call_limit),
        knowledge_retriever=retriever,
        search_knowledge=retriever is not None,
        add_search_knowledge_instructions=retriever is not None,
        # Results are dicts carrying a source and a retrieval time. JSON keeps
        # them intact; the YAML default reflows Turkish text and quotes it
        # inconsistently.
        references_format="json",
        instructions=runtime_instructions(connected, corpus_enabled=corpus_enabled),
        use_instruction_tags=True,
        add_history_to_context=True,
        num_history_runs=int_payload(FLAG_HISTORY_RUNS, default=runtime.scholar_history_runs),
        # Dependencies are rendered into the system instructions. Agno's
        # add_dependencies_to_context option appends them to—and persists them
        # inside—the user message, which corrupts history and leaks metadata to
        # the student-facing transcript.
        add_dependencies_to_context=False,
        resolve_in_context=True,
        add_datetime_to_context=True,
        timezone_identifier="Europe/Istanbul",
        datetime_format="%Y-%m-%d %H:%M (%A)",
        learning=build_learning(model, enabled=runtime.learning_enabled),
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
