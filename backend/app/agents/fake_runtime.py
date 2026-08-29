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


@dataclass
class FakeAgentRuntime:
    containers: dict[str, _FakeContainer] = field(default_factory=dict)

    async def create(self, spec: AgentSpec) -> str:
        self.containers[spec.container_name] = _FakeContainer(running=True)
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
