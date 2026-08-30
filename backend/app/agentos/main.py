"""Entrypoint for the internal AgentOS service."""

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.agentos_enabled:
        raise RuntimeError("AgentOS is disabled; set AGENTOS_ENABLED=true")
    uvicorn.run(
        "app.agentos.app:build_agentos_app",
        host=settings.agentos_host,
        port=settings.agentos_port,
        factory=True,
    )


if __name__ == "__main__":
    main()
