"""An in-memory :class:`AgentRuntime` used for local dev and tests when no
Docker daemon is available. It never touches the network or filesystem;
``healthy()`` simply mirrors whatever state ``create``/``start``/``stop``
left it in.
"""

from dataclasses import dataclass, field

from app.agents.runtime import AgentSpec, RuntimeState


@dataclass
class _FakeContainer:
    running: bool = True
    # Recorded so tests can assert what config a container was built with,
    # the same way they'd inspect a real container's volume.
    mcp_config: str | None = None
    mcp_working_dirs: tuple[str, ...] = ()


@dataclass
class FakeAgentRuntime:
    containers: dict[str, _FakeContainer] = field(default_factory=dict)

    async def create(self, spec: AgentSpec) -> str:
        self.containers[spec.container_name] = _FakeContainer(
            running=True,
            mcp_config=spec.mcp_config,
            mcp_working_dirs=spec.mcp_working_dirs,
        )
        return f"fake-{spec.container_name}"

    async def start(self, spec: AgentSpec) -> None:
        container = self.containers.setdefault(spec.container_name, _FakeContainer(running=False))
        container.running = True

    async def stop(self, spec: AgentSpec, timeout: int = 10) -> None:
        container = self.containers.get(spec.container_name)
        if container is not None:
            container.running = False

    async def destroy(self, spec: AgentSpec) -> None:
        self.containers.pop(spec.container_name, None)

    async def reconfigure(self, spec: AgentSpec) -> None:
        container = self.containers.get(spec.container_name)
        if container is None:
            await self.create(spec)
            return
        container.mcp_config = spec.mcp_config
        container.mcp_working_dirs = spec.mcp_working_dirs
        container.running = True

    async def state(self, spec: AgentSpec) -> RuntimeState:
        container = self.containers.get(spec.container_name)
        if container is None:
            return RuntimeState(exists=False, running=False, container_id=None)
        return RuntimeState(exists=True, running=container.running, container_id=f"fake-{spec.container_name}")

    async def healthy(self, spec: AgentSpec) -> bool:
        container = self.containers.get(spec.container_name)
        return container is not None and container.running

    def endpoint_url(self, spec: AgentSpec) -> str:
        return f"http://{spec.container_name}:{spec.port}"
