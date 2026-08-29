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

    agent_runtime: str = "docker"  # "docker" | "fake"
    docker_network: str = "devrimo-agents"
    hermes_image: str = "devrimo/hermes:latest"
    agent_memory_limit: str = "2g"
    agent_cpu_limit: float = 1.0
    agent_pids_limit: int = 512
    agent_idle_timeout_seconds: int = 1800
    agent_start_timeout_seconds: int = 60
    reconcile_interval_seconds: int = 30
    agent_api_server_port: int = 8642

    agent_openai_base_url: str = ""
    agent_openai_api_key: str = ""

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
