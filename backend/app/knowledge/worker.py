import asyncio
import os
import socket
import uuid

from app.config import get_settings
from app.db.session import SessionLocal
from app.knowledge.ingestion import claim_job, enqueue_due_sources, fail_job, process_job
from app.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


async def run() -> None:
    settings = get_settings()
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    logger.info("knowledge_worker_started", worker_id=worker_id)
    while True:
        async with SessionLocal() as db:
            await enqueue_due_sources(db)
            job = await claim_job(db, worker_id)
            if job is not None:
                try:
                    count = await process_job(db, job)
                    logger.info("knowledge_job_completed", job_id=str(job.id), records=count)
                except Exception as exc:
                    logger.warning("knowledge_job_failed", job_id=str(job.id), error=str(exc))
                    await fail_job(db, job.id, exc)
        if job is None:
            await asyncio.sleep(settings.knowledge_worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(run())
