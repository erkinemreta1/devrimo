import asyncio
import os
import socket
import uuid

from app.config import get_settings
from app.db.models import CampusIngestionJob
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
        job_id = None
        try:
            async with SessionLocal() as db:
                await enqueue_due_sources(db)
                job = await claim_job(db, worker_id)
                job_id = job.id if job is not None else None
            if job_id is not None:
                try:
                    async with SessionLocal() as db:
                        job = await db.get(CampusIngestionJob, job_id)
                        if job is None:
                            raise RuntimeError("Claimed knowledge job disappeared")
                        count = await process_job(db, job)
                    logger.info("knowledge_job_completed", job_id=str(job_id), records=count)
                except Exception as exc:
                    logger.warning("knowledge_job_failed", job_id=str(job_id), error=str(exc))
                    async with SessionLocal() as db:
                        await fail_job(db, job_id, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # A database restart or a migration window must not crash-loop the
            # worker. Compose readiness handles startup ordering; this keeps a
            # running worker resilient to transient database unavailability.
            logger.warning("knowledge_worker_iteration_failed", error=str(exc))
        if job_id is None:
            await asyncio.sleep(settings.knowledge_worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(run())
