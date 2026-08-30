"""The only module in this codebase allowed to import the Docker SDK.

Every agent container runs on an isolated bridge network with no published
ports, no host mounts, and no Docker socket of its own — see
``images/hermes/`` and the compose file for the full hardening story.
"""

import asyncio
import io
import shlex
import tarfile
import time

import docker
import httpx
from docker.errors import APIError, NotFound
from docker.models.containers import Container

from app.agents.runtime import AgentSpec, RuntimeState
from app.campus.mcp_config import MERGE_SCRIPT_PATH, STAGED_CONFIG_PATH, managed_server_names
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

# Idempotent: only touches /opt/data/SOUL.md if the student hasn't already
# customized it, so restarts and re-creates never clobber their edits.
_SEED_SCRIPT = (
    "test -f /opt/data/SOUL.md || cp /opt/devrimo/seed/SOUL.md /opt/data/SOUL.md; "
    "mkdir -p /opt/data/mcp; "
    'if [ -f /opt/data/config.yaml ] && [ -n "$OPENAI_MODEL" ] && '
    '[ "$OPENAI_BASE_URL" = "https://openrouter.ai/api/v1" ]; then '
    'sed -i "s|^  default:.*|  default: \\"$OPENAI_MODEL\\"|; '
    's|^  provider:.*|  provider: \\"openrouter\\"|" /opt/data/config.yaml; '
    "fi; "
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
                existing.reload()
            # Re-install rather than short-circuit: this branch is also the
            # retry path after a create whose config install failed, and a
            # container running a stale campus config is worse than a slow
            # start.
            self._install_mcp_config_sync(existing, spec)
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
        if self._settings.agent_openai_model:
            environment["OPENAI_MODEL"] = self._settings.agent_openai_model

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
            # Hermes' s6 init must switch users/groups and prepare its
            # service and writable data directories during startup. Keep only
            # the capabilities required for those operations.
            cap_add=["SETUID", "SETGID", "CHOWN", "DAC_OVERRIDE", "FOWNER"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=256m"},
            command="gateway run",
        )
        self._seed_data_sync(container)
        self._install_mcp_config_sync(container, spec)
        # The seed script can update Hermes' persisted model configuration, and
        # the campus MCP config is read at gateway start; restart once so the
        # gateway picks up both.
        container.restart()
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

    def _install_mcp_config_sync(self, container: Container, spec: AgentSpec) -> None:
        """Install the student's campus MCP servers into Hermes' config.yaml.

        Hermes reads MCP servers from ``$HERMES_HOME/config.yaml`` under
        ``mcp_servers`` (verified against the real image), so the broker stages
        its rendered mapping as JSON and execs the merge script baked into the
        image, which folds it in with ruamel — preserving Hermes' own comments,
        unrelated keys, and any servers the student added by hand.

        The staged file is uploaded as a tar stream rather than echoed through
        an ``exec`` command line: it embeds the student's METU password, and an
        exec argv is visible to anything that can inspect the daemon. The tar
        header carries mode 0600 so the file is never briefly world-readable,
        and the merge script deletes it once applied.
        """
        if spec.mcp_config is None:
            return

        staged_dir, staged_name = STAGED_CONFIG_PATH.rsplit("/", 1)
        directories = [staged_dir, *spec.mcp_working_dirs]
        mkdir = "mkdir -p " + " ".join(shlex.quote(d) for d in directories)
        exit_code, output = container.exec_run(["sh", "-c", mkdir])
        if exit_code != 0:
            logger.warning(
                "mcp_config_mkdir_failed",
                container=container.name,
                exit_code=exit_code,
                output=output.decode("utf-8", "replace"),
            )
            return

        payload = spec.mcp_config.encode("utf-8")
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            info = tarfile.TarInfo(name=staged_name)
            info.size = len(payload)
            info.mode = 0o600
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(payload))
        archive.seek(0)

        container.put_archive(staged_dir, archive.getvalue())

        # The base image runs Hermes as an unprivileged user; files we drop in
        # as root would otherwise be unreadable to it. Matching /opt/data's own
        # ownership works without this module needing to know that user's uid.
        container.exec_run(
            ["sh", "-c", "chown --reference=/opt/data -R /opt/data/.devrimo 2>/dev/null || true"]
        )

        exit_code, output = container.exec_run(
            [
                "/opt/hermes/.venv/bin/python",
                MERGE_SCRIPT_PATH,
                "--staged",
                STAGED_CONFIG_PATH,
                "--managed",
                ",".join(managed_server_names()),
            ]
        )
        detail = output.decode("utf-8", "replace").strip()
        if exit_code != 0:
            # Leaving a stale toolset in place silently is worse than a loud
            # failure: the student explicitly connected these tools.
            raise RuntimeError(f"Could not apply campus MCP config: {detail}")
        logger.info("mcp_config_applied", container=container.name, detail=detail)

    async def create(self, spec: AgentSpec) -> str:
        return await self._run(self._create_sync, spec)

    async def reconfigure(self, spec: AgentSpec) -> None:
        def _reconfigure() -> None:
            container = self._get_container(spec)
            if container is None:
                # Nothing to reconfigure; create it with the new config instead.
                self._create_sync(spec)
                return
            if container.status != "running":
                # The install goes through `exec`, which needs a live container.
                container.start()
                container.reload()
            self._install_mcp_config_sync(container, spec)
            # The gateway reads the MCP config at start.
            container.restart()

        await self._run(_reconfigure)

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
