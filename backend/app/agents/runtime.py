"""The seam between the agent state machine and whatever actually runs containers.

Every other module talks to :class:`AgentRuntime`, never to a specific
container engine. Swapping Docker for Nomad or Kubernetes later means
writing one new implementation of this protocol, not touching the manager,
the API routes, or the reconciler.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class AgentSpec:
    """Everything needed to create or address one user's agent container."""

    user_id: UUID
    container_name: str
    volume_name: str
    image: str
    api_key: str
    port: int


@dataclass(frozen=True)
class RuntimeState:
    exists: bool
    running: bool
    container_id: str | None


class AgentRuntime(Protocol):
    """Async lifecycle operations for a single user's agent container."""

    async def create(self, spec: AgentSpec) -> str:
        """Create the volume and container (if missing) and start it. Returns the container id."""
        ...

    async def start(self, spec: AgentSpec) -> None:
        """Start an existing, stopped container."""
        ...

    async def stop(self, spec: AgentSpec, timeout: int = 10) -> None:
        """Gracefully stop a running container. The volume is untouched."""
        ...

    async def destroy(self, spec: AgentSpec) -> None:
        """Stop and remove the container and its volume. Irreversible."""
        ...

    async def state(self, spec: AgentSpec) -> RuntimeState:
        """Inspect current container existence/running state."""
        ...

    async def healthy(self, spec: AgentSpec) -> bool:
        """Whether the container's Hermes API server is responding."""
        ...

    def endpoint_url(self, spec: AgentSpec) -> str:
        """The base URL the broker should use to reach this container."""
        ...
