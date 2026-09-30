import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("j"))
    mode: Mapped[str] = mapped_column(String(16), default="speech")  # speech | video
    max_file_size_mb: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    files: Mapped[list["File"]] = relationship(back_populates="job", order_by="File.created_at")


class File(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("f"))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    parent_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"))
    original_name: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(255), unique=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # FileStatus = PRD JobStatus: UPLOADING | QUEUED | ANALYZING | READY | REVIEW_REQUIRED | NOT_READY
    #              | FIXING | VERIFYING | COMPLETED | FAILED | EXPIRED
    status: Mapped[str] = mapped_column(String(24), default="UPLOADING")
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    job: Mapped[Job] = relationship(back_populates="files")


class Diagnostic(Base):
    __tablename__ = "diagnostics"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("d"))
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")  # QUEUED | RUNNING | DONE | FAILED
    overall_status: Mapped[str | None] = mapped_column(String(24))
    ruleset_version: Mapped[str | None] = mapped_column(String(16))
    results_json: Mapped[list | None] = mapped_column(JSON)
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(48))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FixJob(Base):
    __tablename__ = "fix_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("x"))
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), index=True)
    fix_id: Mapped[str] = mapped_column(String(16))
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")  # QUEUED | RUNNING | SUCCEEDED | REJECTED | FAILED
    output_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"))
    verification_id: Mapped[str | None] = mapped_column(ForeignKey("diagnostics.id"))
    checks_json: Mapped[list | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(48))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("e"))
    job_id: Mapped[str | None] = mapped_column(String(32), index=True)
    file_id: Mapped[str | None] = mapped_column(String(32))
    event_name: Mapped[str] = mapped_column(String(48), index=True)
    properties_json: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def create_event(session, name: str, job_id=None, file_id=None, **properties):
    session.add(Event(event_name=name, job_id=job_id, file_id=file_id, properties_json=properties))


def init_db():
    # ponytail: create_all 대신 Alembic migration은 스키마 변경이 생길 때 도입
    Base.metadata.create_all(engine)
