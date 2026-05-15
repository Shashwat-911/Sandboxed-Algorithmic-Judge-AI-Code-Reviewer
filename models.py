import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum as SAEnum, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class SubmissionStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    COMPILE_ERROR = "COMPILE_ERROR"
    ERROR = "ERROR"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id = Column(String(255), nullable=False, index=True)
    language = Column(String(50), nullable=False)
    code = Column(Text, nullable=False)
    status = Column(
        SAEnum(SubmissionStatus, name="submissionstatus"),
        nullable=False,
        default=SubmissionStatus.PENDING,
    )
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    execution_time_ms = Column(Float, nullable=True)
    ai_feedback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Submission id={self.id} lang={self.language} status={self.status}>"
