import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.pool import reset_pool
from app.agents.reconciler import run_reconciler_loop
from app.api.v1 import router as api_v1_router
from app.api.v1.admin import sync_directory
from app.campus.manifest import commits_by_slug
from app.campus.sources.ingest import run_ingest_loop
from app.config import get_settings
from app.db.session import SessionLocal
from app.logging import configure_logging, get_logger
from app.observability import ObservabilityMiddleware, capture_exception, get_posthog
from app.observability.client import shutdown as posthog_shutdown
from app.observability.logs import shutdown as posthog_logs_shutdown

configure_logging()
logger = get_logger(__name__)


async def _run_directory_sync_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    if not settings.supabase_secret_key or not settings.supabase_url:
        return
    while not stop_event.is_set():
        try:
            async with SessionLocal() as db:
                synced = await sync_directory(db)
            logger.info("admin_directory_synced", users=synced)
        except Exception as exc:
            logger.warning("admin_directory_sync_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.admin_directory_sync_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.agent_tracing_enabled:
        # OpenInference redaction flags are set in deployment configuration.
        # This exporter writes to our Agno DB; it does not send traces to Agno.
        from agno.tracing import setup_tracing

        from app.agents.store import get_agno_db

        setup_tracing(db=get_agno_db(), batch_processing=True)
    # Constructed eagerly so a missing or mis-configured key is reported at
    # boot rather than discovered later as an absence of data.
    get_posthog()
    stop_event = asyncio.Event()
    reconciler_task = asyncio.create_task(run_reconciler_loop(stop_event))
    directory_sync_task = asyncio.create_task(_run_directory_sync_loop(stop_event))
    # Keeps the public campus corpus current. Independent of the reconciler
    # because it fails differently: a campus site being down is routine and
    # per-source, while the reconciler's job is holding student credentials.
    ingest_task = asyncio.create_task(run_ingest_loop(stop_event))
    logger.info("startup_complete")
    try:
        yield
    finally:
        stop_event.set()
        await reconciler_task
        await directory_sync_task
        await ingest_task
        # Every resident agent is holding MCP subprocesses that have a
        # student's METU credentials in their environment; leaving them
        # parented to a dead broker is not acceptable.
        await reset_pool()
        # Last, so anything the teardown above reported is still flushed. An
        # unflushed queue at SIGTERM loses exactly the events that explain
        # why the process is going away.
        await asyncio.to_thread(posthog_shutdown)
        await asyncio.to_thread(posthog_logs_shutdown)


app = FastAPI(title="Devrimo Agent Broker", lifespan=lifespan)

settings = get_settings()
# Added first, so it sits *inside* CORSMiddleware: Starlette applies middleware
# in reverse, and CORS headers must survive on responses this one observes.
app.add_middleware(ObservabilityMiddleware)
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
    # The log line above carries no traceback. This does, plus the request id,
    # user id and session bound by ObservabilityMiddleware.
    capture_exception(exc, path=request.url.path, method=request.method, handler="unhandled_exception")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error"})
