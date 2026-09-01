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
    # Supabase secret key (or legacy service-role key). Backend only.
    supabase_secret_key: str = ""
    admin_bootstrap_user_ids: str = ""
    admin_directory_sync_seconds: int = 300
    posthog_dashboard_url: str = ""

    # --- Agent runtime -----------------------------------------------------
    # "agno" runs a real Agno agent with real MCP subprocesses. "fake" swaps in
    # a scripted agent so the whole API can be exercised in tests and local dev
    # without a model provider or the four campus servers installed.
    agent_runtime: str = "agno"  # "agno" | "fake"
    # Scholar is the production-hardened profile. Legacy remains available as
    # an explicit rollback target while a deployment completes its eval gates.
    agent_profile: str = "scholar"  # "scholar" | "legacy"

    agent_model: str = "muse-spark-1.2-contributor"
    agent_openai_base_url: str = "https://opencode.ai/zen/go/v1"
    agent_openai_api_key: str = ""
    agent_max_tokens: int = 32768

    # How many prior runs of a session are replayed into the model's context.
    agent_history_runs: int = 10
    scholar_history_runs: int = 3
    agent_tool_call_limit: int = 10
    agent_compress_tool_results: bool = True
    agent_compress_tool_results_limit: int = 3
    agent_learning_enabled: bool = True
    agent_retries: int = 2
    agent_store_events: bool = False
    agent_tracing_enabled: bool = False
    # A user's agent (and its MCP subprocesses) is torn down after this long
    # with no turns. Nothing is lost — history lives in the database.
    agent_idle_timeout_seconds: int = 900
    # Ceiling on simultaneously-resident users. The least recently used agent
    # is evicted past this, so a busy hour can't spawn unbounded subprocesses.
    agent_pool_max_size: int = 64
    reconcile_interval_seconds: int = 60
    turn_lock_lease_seconds: int = 180
    turn_lock_heartbeat_seconds: int = 60

    # --- Observability (PostHog) -------------------------------------------
    # Everything below is optional: with no key the whole integration is a
    # no-op, so a developer without a PostHog project still gets a working
    # broker. ``posthog_debug`` makes that silence loud during development.
    posthog_api_key: str = ""  # phc_...
    posthog_host: str = "https://eu.i.posthog.com"
    # Only needed for local feature-flag evaluation, which avoids a network
    # round trip per flag check on the chat hot path.
    posthog_personal_api_key: str = ""  # phx_...
    posthog_enabled: bool = True
    posthog_debug: bool = False
    # The model is served from an OpenAI-compatible endpoint PostHog has no
    # price table for, so cost is reported from these instead of inferred.
    # Prices are per single token, not per million.
    posthog_input_token_price: float = 0.0
    posthog_output_token_price: float = 0.0

    # --- Campus MCP servers ------------------------------------------------
    # Where the four per-server virtualenvs live on the broker host. The image
    # build installs each one at ``{campus_mcp_root}/{slug}/.venv``.
    campus_mcp_root: str = "/opt/mcp"
    # Per-user scratch root. Servers that cache a session token relative to
    # their CWD (odtuclass) get a private directory beneath this.
    campus_state_root: str = "/var/lib/devrimo/campus"
    campus_mcp_timeout_seconds: int = 30

    # --- Campus knowledge (public campus content) --------------------------
    # The corpus of public METU content the agent can search. Distinct from the
    # campus MCP servers above in every way that matters: it is shared rather
    # than per-student, carries no credentials, and is built from sources that
    # admins configure at runtime rather than from this file.
    campus_knowledge_enabled: bool = True
    campus_ingest_interval_seconds: int = 300
    # How long a source may hold the ingest loop. A slow site must not be able
    # to starve the other sources on the same tick.
    campus_ingest_source_timeout_seconds: int = 300
    campus_fetch_timeout_seconds: int = 20
    campus_fetch_max_bytes: int = 4_000_000
    campus_fetch_user_agent: str = "DevrimoBot/1.0 (+https://devrimo.metu.edu.tr/bot)"
    # Hosts the fetcher may talk to at all, as comma-separated patterns. Source
    # rows are admin-editable, so this is the boundary that keeps a compromised
    # admin account from pointing the fetcher at the broker's own network — see
    # app/campus/sources/fetch.py.
    campus_fetch_allowed_hosts: str = "*.metu.edu.tr"
    campus_fetch_default_crawl_delay_seconds: float = 1.0
    campus_fetch_max_crawl_delay_seconds: float = 15.0

    campus_knowledge_table: str = "campus_documents"
    campus_knowledge_schema: str = "ai"
    campus_knowledge_max_results: int = 8

    # Embeddings are bought from an OpenAI-compatible endpoint. Left empty the
    # whole knowledge layer reports itself unconfigured and Scholar is built
    # exactly as it is today, which is what keeps local development cheap.
    # Changing the model or the dimension invalidates every stored vector; the
    # admin surface offers a reindex for exactly that reason.
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_dimensions: int = 1536

    secret_encryption_key: str = "change-me-to-a-real-generated-secret"

    # --- AgentOS -----------------------------------------------------------
    # AgentOS runs as a separate, internal process. Production authorization
    # uses JWT/RBAC; the old shared OS security key is intentionally not used.
    agentos_enabled: bool = False
    agentos_host: str = "127.0.0.1"
    agentos_port: int = 7777
    agentos_jwt_verification_key: str = ""
    agentos_jwks_file: str = ""
    agentos_jwt_algorithm: str = "RS256"
    agentos_jwt_audience: str = "devrimo"
    agentos_admin_scope: str = "agentos:admin"
    agentos_cors_origins: str = "https://os.agno.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def posthog_configured(self) -> bool:
        return bool(self.posthog_enabled and self.posthog_api_key)

    @property
    def agentos_cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.agentos_cors_origins.split(",") if origin.strip()]

    @property
    def campus_fetch_allowed_host_patterns(self) -> list[str]:
        return [value.strip().lower() for value in self.campus_fetch_allowed_hosts.split(",") if value.strip()]

    @property
    def database_is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres+", "postgres:"))

    @property
    def knowledge_configured(self) -> bool:
        """Whether a real vector-backed corpus can be built.

        Three things have to hold at once, and any of them missing is a normal
        state rather than an error: the operator has not turned it off, the
        database is Postgres (pgvector has no SQLite equivalent, and the test
        suite runs on SQLite), and an embedding key exists.
        """
        return bool(self.campus_knowledge_enabled and self.database_is_postgres and self.embedding_api_key)

    @property
    def admin_bootstrap_ids(self) -> set[str]:
        return {value.strip() for value in self.admin_bootstrap_user_ids.split(",") if value.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
