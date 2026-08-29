"""The only module in this codebase allowed to import the Docker SDK.

Every agent container runs on an isolated bridge network with no published
ports, no host mounts, and no Docker socket of its own — see
``images/hermes/`` and the compose file for the full hardening story.
"""

import asyncio

import docker
import httpx
from docker.errors import APIError, NotFound
from docker.models.containers import Container

from app.agents.runtime import AgentSpec, RuntimeState
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

# Idempotent: only touches /opt/data/SOUL.md if the student hasn't already
# customized it, so restarts and re-creates never clobber their edits.
_SEED_SCRIPT = (
    "test -f /opt/data/SOUL.md || cp /opt/devrimo/seed/SOUL.md /opt/data/SOUL.md; "
    "mkdir -p /opt/data/mcp; "
    "test -f /opt/data/mcp/campus.mcp.json.example || "
    "cp /opt/devrimo/seed/campus.mcp.json.example /opt/data/mcp/campus.mcp.json.example; "
    "true"
)


class DockerAgentRuntime:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = docker.from_env()
        self._ensure_network()

    def _ensure_network(self) -> None:
        # Falls back to creating this network only if it doesn't exist yet —
        # in the normal docker-compose setup it's pre-created there (with
        # this exact name; see the comment on `devrimo-agents` in
        # docker-compose.yml) so this path only matters for bare `docker
        # run`/standalone use. Plain bridge, not `internal=True`: agents
        # need outbound access to reach AGENT_OPENAI_BASE_URL.
        try:
            self._client.networks.get(self._settings.docker_network)
        except NotFound:
            self._client.networks.create(self._settings.docker_network, driver="bridge")

    async def _run(self, fn, /, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _get_container(self, spec: AgentSpec) -> Container | None:
        try:
            return self._client.containers.get(spec.container_name)
        except NotFound:
            return None

    def _ensure_volume_sync(self, spec: AgentSpec) -> None:
        try:
            self._client.volumes.get(spec.volume_name)
        except NotFound:
            self._client.volumes.create(spec.volume_name)

    def _create_sync(self, spec: AgentSpec) -> str:
        self._ensure_volume_sync(spec)

        existing = self._get_container(spec)
        if existing is not None:
            if existing.status != "running":
                existing.start()
            return existing.id

        environment = {
            "API_SERVER_ENABLED": "true",
            "API_SERVER_HOST": "0.0.0.0",
            "API_SERVER_PORT": str(spec.port),
            "API_SERVER_KEY": spec.api_key,
        }
        if self._settings.agent_openai_base_url:
            environment["OPENAI_BASE_URL"] = self._settings.agent_openai_base_url
        if self._settings.agent_openai_api_key:
            environment["OPENAI_API_KEY"] = self._settings.agent_openai_api_key

        container = self._client.containers.run(
            spec.image,
            name=spec.container_name,
            detach=True,
            network=self._settings.docker_network,
            restart_policy={"Name": "unless-stopped"},
            volumes={spec.volume_name: {"bind": "/opt/data", "mode": "rw"}},
            environment=environment,
            mem_limit=self._settings.agent_memory_limit,
            memswap_limit=self._settings.agent_memory_limit,
            nano_cpus=int(self._settings.agent_cpu_limit * 1_000_000_000),
            pids_limit=self._settings.agent_pids_limit,
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=256m"},
            command="gateway run",
        )
        self._seed_data_sync(container)
        return container.id

    def _seed_data_sync(self, container: Container) -> None:
        """Best-effort: copy the baked-in persona/config into /opt/data on first boot.

        Not load-bearing — Hermes runs fine on its defaults if this fails, so a
        failure here is logged and swallowed rather than failing provisioning.
        """
        try:
            exit_code, output = container.exec_run(["sh", "-c", _SEED_SCRIPT])
            if exit_code != 0:
                logger.warning(
                    "seed_data_failed",
                    container=container.name,
                    exit_code=exit_code,
                    output=output.decode("utf-8", "replace"),
                )
        except APIError as exc:
            logger.warning("seed_data_failed", container=container.name, error=str(exc))

    async def create(self, spec: AgentSpec) -> str:
        return await self._run(self._create_sync, spec)

    async def start(self, spec: AgentSpec) -> None:
        def _start() -> None:
            container = self._get_container(spec)
            if container is None:
                self._create_sync(spec)
                return
            if container.status != "running":
                container.start()

        await self._run(_start)

    async def stop(self, spec: AgentSpec, timeout: int = 10) -> None:
        def _stop() -> None:
            container = self._get_container(spec)
            if container is not None and container.status == "running":
                container.stop(timeout=timeout)

        await self._run(_stop)

    async def destroy(self, spec: AgentSpec) -> None:
        def _destroy() -> None:
            container = self._get_container(spec)
            if container is not None:
                try:
                    container.remove(force=True)
                except APIError:
                    logger.warning("container_remove_failed", container=spec.container_name)
            try:
                self._client.volumes.get(spec.volume_name).remove(force=True)
            except NotFound:
                pass

        await self._run(_destroy)

    async def state(self, spec: AgentSpec) -> RuntimeState:
        def _state() -> RuntimeState:
            container = self._get_container(spec)
            if container is None:
                return RuntimeState(exists=False, running=False, container_id=None)
            container.reload()
            return RuntimeState(exists=True, running=container.status == "running", container_id=container.id)

        return await self._run(_state)

    async def healthy(self, spec: AgentSpec) -> bool:
        url = f"{self.endpoint_url(spec)}/health"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    def endpoint_url(self, spec: AgentSpec) -> str:
        return f"http://{spec.container_name}:{spec.port}"
