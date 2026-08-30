"""JWT/RBAC-protected AgentOS over Devrimo's self-hosted Agno database."""

from pathlib import Path

from agno.os import AgentOS
from agno.os.config import AuthorizationConfig
from agno.os.settings import AgnoAPISettings

from app.agents.store import get_agno_db
from app.config import get_settings


def build_agentos_app():
    settings = get_settings()
    if not settings.agentos_enabled:
        raise RuntimeError("AgentOS is disabled; set AGENTOS_ENABLED=true in the dedicated service")
    verification_key = settings.agentos_jwt_verification_key.strip().replace("\\n", "\n")
    verification_key_file = settings.agentos_jwt_verification_key_file.strip()
    if verification_key_file:
        verification_key = Path(verification_key_file).read_text(encoding="utf-8").strip()
    jwks_file = settings.agentos_jwks_file.strip()
    if not verification_key and not jwks_file:
        raise RuntimeError(
            "AGENTOS_JWT_VERIFICATION_KEY, AGENTOS_JWT_VERIFICATION_KEY_FILE, or AGENTOS_JWKS_FILE is required"
        )

    agent_os = AgentOS(
        id="devrimo",
        name="Devrimo AgentOS",
        description="Internal, read-oriented operations surface for Scholar runs, evals, metrics, and traces.",
        db=get_agno_db(),
        # Deliberately register no runnable credential-bearing agent. Production
        # Scholar runs in the broker and writes sessions/traces to the shared DB.
        agents=[],
        authorization=True,
        authorization_config=AuthorizationConfig(
            verification_keys=[verification_key] if verification_key else None,
            jwks_file=jwks_file or None,
            algorithm=settings.agentos_jwt_algorithm,
            verify_audience=settings.agentos_verify_audience,
            audience=settings.agentos_jwt_audience if settings.agentos_verify_audience else None,
            admin_scope=settings.agentos_admin_scope,
            user_isolation=True,
        ),
        settings=AgnoAPISettings(
            env="production",
            docs_enabled=False,
            authorization_enabled=True,
            cors_origin_list=settings.agentos_cors_origin_list,
        ),
        tracing=False,
        telemetry=False,
        auto_provision_dbs=True,
    )
    return agent_os.get_app()
