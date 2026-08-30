"""Agent profile dispatch."""

from uuid import UUID

from agno.agent import Agent
from agno.tools.mcp import MCPTools

from app.agents.legacy import build_legacy_agent
from app.config import get_settings


def build_agent(user_id: UUID, connected: list[MCPTools]) -> Agent:
    profile = get_settings().agent_profile.lower()
    if profile == "legacy":
        return build_legacy_agent(user_id, connected)
    if profile == "scholar":
        from app.agents.scholar.build import build_scholar_agent

        return build_scholar_agent(connected)
    raise ValueError(f"Unknown AGENT_PROFILE: {profile!r}")
