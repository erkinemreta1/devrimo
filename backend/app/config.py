from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:3000"

    database_url: str = "sqlite+aiosqlite:///./devrimo.db"

    supabase_url: str = ""
    supabase_jwt_secret: str = ""

    # --- Agent runtime -----------------------------------------------------
    # "agno" runs a real Agno agent with real MCP subprocesses. "fake" swaps in
    # a scripted agent so the whole API can be exercised in tests and local dev
    # without a model provider or the four campus servers installed.
    agent_runtime: str = "agno"  # "agno" | "fake"

    agent_model: str = "muse-spark-1.2-contributor"
    agent_openai_base_url: str = "https://opencode.ai/zen/go/v1"
    agent_openai_api_key: str = ""
    agent_max_tokens: int = 32768

    # How many prior runs of a session are replayed into the model's context.
    agent_history_runs: int = 10
    # A user's agent (and its MCP subprocesses) is torn down after this long
    # with no turns. Nothing is lost — history lives in the database.
    agent_idle_timeout_seconds: int = 900
    # Ceiling on simultaneously-resident users. The least recently used agent
    # is evicted past this, so a busy hour can't spawn unbounded subprocesses.
    agent_pool_max_size: int = 64
    reconcile_interval_seconds: int = 60

    # --- Campus MCP servers ------------------------------------------------
    # Where the four per-server virtualenvs live on the broker host. The image
    # build installs each one at ``{campus_mcp_root}/{slug}/.venv``.
    campus_mcp_root: str = "/opt/mcp"
    # Per-user scratch root. Servers that cache a session token relative to
    # their CWD (odtuclass) get a private directory beneath this.
    campus_state_root: str = "/var/lib/devrimo/campus"
    campus_mcp_timeout_seconds: int = 30

    secret_encryption_key: str = "change-me-to-a-real-generated-secret"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
