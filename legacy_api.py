"""
main.py — FastAPI gateway for the Sandboxed Algorithmic Judge.

Endpoints:
  POST /submit          — Accept a code submission, return a job_id.
  GET  /status/{job_id} — Poll execution status and results.
  GET  /health          — Liveness probe for Docker/load-balancer.
"""

import logging
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from config import settings
from database import engine, get_db
from models import Base, Submission, SubmissionStatus
from sandbox import LANGUAGE_CONFIGS

log = logging.getLogger(__name__)

# ─── FastAPI application ──────────────────────────────────────────────────────

app = FastAPI(
    title="Sandboxed Algorithmic Judge",
    description=(
        "Secure remote code execution engine with AI-powered complexity analysis. "
        "Submissions are executed in isolated Docker containers with strict resource limits."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup() -> None:
    """Create all SQLAlchemy tables (idempotent)."""
    Base.metadata.create_all(bind=engine)
    log.info("Database tables initialised.")


# ─── Schemas ──────────────────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = set(LANGUAGE_CONFIGS.keys())


class SubmissionRequest(BaseModel):
    problem_id: str = Field(..., min_length=1, max_length=255, example="two-sum-001")
    language: str = Field(..., example="python")
    code: str = Field(..., min_length=1, max_length=65_536, example='print("Hello")')

    @field_validator("language")
    @classmethod
    def language_must_be_supported(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language '{v}'. "
                f"Supported: {sorted(SUPPORTED_LANGUAGES)}"
            )
        return v


class SubmissionResponse(BaseModel):
    job_id: str
    status: str
    message: str = "Submission queued for execution."


class StatusResponse(BaseModel):
    job_id: str
    problem_id: str
    language: str
    status: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    execution_time_ms: Optional[float] = None
    ai_feedback: Optional[str] = None
    created_at: str
    updated_at: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.post(
    "/submit",
    response_model=SubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit code for sandboxed execution",
    tags=["Judge"],
)
def submit_code(request: SubmissionRequest) -> SubmissionResponse:
    """
    Accept a code submission:
    1. Persist a PENDING record to PostgreSQL.
    2. Enqueue the Celery task (imported here to avoid circular imports).
    3. Return the `job_id` immediately — execution is asynchronous.
    """
    # Import here to avoid a module-level circular import between main ↔ worker
    from worker import execute_submission

    job_id = str(uuid.uuid4())

    # Persist before enqueue so GET /status never returns 404 for a valid job
    with get_db() as db:
        submission = Submission(
            id=job_id,
            problem_id=request.problem_id,
            language=request.language,
            code=request.code,
            status=SubmissionStatus.PENDING,
        )
        db.add(submission)

    log.info("Queuing job %s  lang=%s  problem=%s", job_id, request.language, request.problem_id)

    # .delay() enqueues to Redis; worker picks it up asynchronously
    try:
        execute_submission.delay(job_id=job_id, code=request.code, language=request.language)
    except Exception:
        with get_db() as db:
            row = db.get(Submission, job_id)
            row.status = SubmissionStatus.ERROR
            row.stderr = "Queue unavailable; submission was not dispatched."
        raise HTTPException(503, "Execution queue unavailable. Retry later.")


    return SubmissionResponse(job_id=job_id, status=SubmissionStatus.PENDING)


@app.get(
    "/status/{job_id}",
    response_model=StatusResponse,
    summary="Poll submission status and results",
    tags=["Judge"],
)
def get_status(job_id: str) -> StatusResponse:
    """Return the current state of a submission. Poll until status is terminal."""
    try:
        uuid.UUID(job_id)   # Validate format before hitting the DB
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format — must be a UUID.",
        )

    with get_db() as db:
        row: Optional[Submission] = db.get(Submission, job_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No submission found with job_id={job_id}",
        )

    return StatusResponse(
        job_id=str(row.id),
        problem_id=row.problem_id,
        language=row.language,
        status=row.status,
        stdout=row.stdout,
        stderr=row.stderr,
        execution_time_ms=row.execution_time_ms,
        ai_feedback=row.ai_feedback,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@app.get(
    "/health",
    summary="Liveness probe",
    tags=["Ops"],
    status_code=status.HTTP_200_OK,
)
def health_check() -> dict:
    return {"status": "ok", "service": "sandboxed-judge-api"}
