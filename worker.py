"""
worker.py — Celery task: pick up a submission, run it in the sandbox,
optionally get an AI review, and persist results to PostgreSQL.
"""

import logging

from celery import Celery
from celery.utils.log import get_task_logger

from ai_reviewer import get_ai_review
from config import settings
from database import get_db
from models import Submission, SubmissionStatus
from sandbox import DockerSandbox

# ─── Celery application ───────────────────────────────────────────────────────

celery_app = Celery(
    "judge_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Prevent a zombie task from holding a DB row in RUNNING forever
    task_soft_time_limit=90,
    task_time_limit=120,
    worker_prefetch_multiplier=1,   # One task at a time per worker process
    task_acks_late=True,            # ACK only after task completes (safer retries)
)

log: logging.Logger = get_task_logger(__name__)


# ─── Helper ───────────────────────────────────────────────────────────────────

def _update_submission(job_id: str, **kwargs) -> None:
    """Update a Submission row inside a fresh session."""
    with get_db() as db:
        row: Submission | None = db.get(Submission, job_id)
        if row is None:
            log.error("Submission %s not found in DB — cannot update.", job_id)
            return
        for key, value in kwargs.items():
            setattr(row, key, value)
        # updated_at is handled by the onupdate hook in models.py


# ─── Task ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="worker.execute_submission",
    max_retries=0,          # Do NOT retry code execution — non-idempotent
    acks_late=True,
)
def execute_submission(self, job_id: str, code: str, language: str) -> dict:
    """
    Main Celery task:
      1. Mark submission RUNNING.
      2. Execute code in the Docker sandbox.
      3. If execution succeeded → request AI review.
      4. Persist final state to PostgreSQL.
    Returns a summary dict for the Celery result backend (optional inspection).
    """
    log.info("▶ Starting job %s  lang=%s", job_id, language)

    # ── 1. Mark as RUNNING ────────────────────────────────────────────────────
    try:
        _update_submission(job_id, status=SubmissionStatus.RUNNING)
    except Exception as exc:
        log.exception("Failed to mark job %s RUNNING: %s", job_id, exc)
        # Continue — don't abort the actual execution over a DB hiccup

    # ── 2. Execute in sandbox ─────────────────────────────────────────────────
    sandbox = DockerSandbox()
    try:
        result = sandbox.run(code=code, language=language)
    except Exception as exc:
        log.exception("Sandbox raised an unhandled exception for job %s", job_id)
        _update_submission(
            job_id,
            status=SubmissionStatus.ERROR,
            stderr=f"Internal sandbox error: {exc}",
        )
        return {"job_id": job_id, "status": "ERROR"}

    log.info(
        "✓ Sandbox finished  job=%s  status=%s  time=%.2f ms",
        job_id, result.status, result.execution_time_ms,
    )

    # ── 3. Map sandbox status → DB status ────────────────────────────────────
    status_map = {
        "SUCCESS":       SubmissionStatus.SUCCESS,
        "FAILED":        SubmissionStatus.FAILED,
        "TIMEOUT":       SubmissionStatus.TIMEOUT,
        "COMPILE_ERROR": SubmissionStatus.COMPILE_ERROR,
        "ERROR":         SubmissionStatus.ERROR,
    }
    db_status = status_map.get(result.status, SubmissionStatus.ERROR)

    # ── 4. AI review (only on clean exit) ─────────────────────────────────────
    ai_feedback: str | None = None
    if result.status == "SUCCESS":
        log.info("Requesting AI review for job %s …", job_id)
        try:
            ai_feedback = get_ai_review(
                code=code,
                language=language,
                stdout=result.stdout,
                exit_code=result.exit_code,
                execution_time_ms=result.execution_time_ms,
            )
        except Exception as exc:
            log.warning("AI review failed for job %s: %s", job_id, exc)
            ai_feedback = f"AI review unavailable: {exc}"

    # ── 5. Persist final record ───────────────────────────────────────────────
    try:
        _update_submission(
            job_id,
            status=db_status,
            stdout=result.stdout or None,
            stderr=result.stderr or None,
            execution_time_ms=result.execution_time_ms if result.execution_time_ms else None,
            ai_feedback=ai_feedback,
        )
    except Exception as exc:
        log.exception("Failed to persist results for job %s: %s", job_id, exc)

    log.info("■ Job %s complete — %s", job_id, db_status)
    return {
        "job_id": job_id,
        "status": db_status,
        "execution_time_ms": result.execution_time_ms,
    }
