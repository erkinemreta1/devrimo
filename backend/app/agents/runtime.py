from dataclasses import asdict, dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.planning import GradePolicy
from app.config import get_settings
from app.db.models import AgentRuntimeSettings


@dataclass(frozen=True)
class AgentRuntimeConfig:
    model_id: str
    profile: str
    max_tokens: int
    legacy_history_runs: int
    scholar_history_runs: int
    tool_call_limit: int
    learning_enabled: bool
    input_token_price: float
    output_token_price: float
    revision: int
    knowledge_enabled: bool = True
    knowledge_max_results: int = 8
    # The grading rules the semester planner is built with. Held here because
    # an agent is constructed with them, so a policy edit has to invalidate a
    # resident agent exactly as a model change does.
    grade_policy: GradePolicy = field(default_factory=GradePolicy)
    policy_revision: int = 0

    def as_dict(self) -> dict:
        data = asdict(self)
        # The policy is reported by its own admin endpoint; flattening the whole
        # letter scale into every runtime response and audit record would bury
        # the change that was actually made.
        data.pop("grade_policy", None)
        return data

    @property
    def cache_key(self) -> tuple:
        """What the agent pool compares to decide whether a rebuild is due.

        A tuple rather than a single revision because two independent rows now
        feed one agent, and summing their revisions would make a bump in each
        cancel out.
        """
        return (self.revision, self.policy_revision)


def default_runtime_config() -> AgentRuntimeConfig:
    settings = get_settings()
    return AgentRuntimeConfig(
        model_id=settings.agent_model,
        profile=settings.agent_profile,
        max_tokens=settings.agent_max_tokens,
        legacy_history_runs=settings.agent_history_runs,
        scholar_history_runs=settings.scholar_history_runs,
        tool_call_limit=settings.agent_tool_call_limit,
        learning_enabled=settings.agent_learning_enabled,
        input_token_price=settings.posthog_input_token_price,
        output_token_price=settings.posthog_output_token_price,
        revision=0,
        knowledge_enabled=settings.campus_knowledge_enabled,
        knowledge_max_results=settings.campus_knowledge_max_results,
    )


async def get_runtime_config(db: AsyncSession) -> AgentRuntimeConfig:
    settings = get_settings()
    row = await db.get(AgentRuntimeSettings, "default")
    # Imported here rather than at module scope: app.campus.policy imports the
    # planning tool, which would otherwise close an import cycle through this
    # module.
    from app.campus.policy import load_grade_policy

    grade_policy, policy_revision = await load_grade_policy(db)
    return AgentRuntimeConfig(
        knowledge_enabled=(
            row.knowledge_enabled if row and row.knowledge_enabled is not None else settings.campus_knowledge_enabled
        ),
        knowledge_max_results=(
            row.knowledge_max_results
            if row and row.knowledge_max_results is not None
            else settings.campus_knowledge_max_results
        ),
        grade_policy=grade_policy,
        policy_revision=policy_revision,
        model_id=row.model_id if row and row.model_id else settings.agent_model,
        profile=row.profile if row and row.profile else settings.agent_profile,
        max_tokens=row.max_tokens if row and row.max_tokens is not None else settings.agent_max_tokens,
        legacy_history_runs=(
            row.legacy_history_runs if row and row.legacy_history_runs is not None else settings.agent_history_runs
        ),
        scholar_history_runs=(
            row.scholar_history_runs if row and row.scholar_history_runs is not None else settings.scholar_history_runs
        ),
        tool_call_limit=(
            row.tool_call_limit if row and row.tool_call_limit is not None else settings.agent_tool_call_limit
        ),
        learning_enabled=(
            row.learning_enabled if row and row.learning_enabled is not None else settings.agent_learning_enabled
        ),
        input_token_price=(
            row.input_token_price if row and row.input_token_price is not None else settings.posthog_input_token_price
        ),
        output_token_price=(
            row.output_token_price
            if row and row.output_token_price is not None
            else settings.posthog_output_token_price
        ),
        revision=row.revision if row else 0,
    )
