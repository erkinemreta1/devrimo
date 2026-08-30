import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.pool import reset_pool
from app.agents.reconciler import run_reconciler_loop
from app.api.v1 import router as api_v1_router
from app.campus.manifest import commits_by_slug
from app.config import get_settings
from app.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    reconciler_task = asyncio.create_task(run_reconciler_loop(stop_event))
    logger.info("startup_complete")
    try:
        yield
    finally:
        stop_event.set()
        await reconciler_task
        # Every resident agent is holding MCP subprocesses that have a
        # student's METU credentials in their environment; leaving them
        # parented to a dead broker is not acceptable.
        await reset_pool()


app = FastAPI(title="Devrimo Agent Broker", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def root_health() -> dict[str, object]:
    """Liveness, plus which commit each campus MCP server was built from.

    The commits are reported because the servers are pinned by build arg and
    the build deletes their ``.git`` directories: without this, the pin is
    unverifiable from a running container. They name public commits in public
    repositories, so exposing them unauthenticated discloses nothing that
    reading those repositories would not — and the alternative, guessing which
    image is deployed during an incident, is worse.
    """
    return {"status": "ok", "campus_servers": commits_by_slug(settings.campus_mcp_root)}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error"})
