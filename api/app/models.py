"""Postgres index. Full call traces live in S3; these tables hold only what we list and group."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    """Top level of the hierarchy: project > volume (conversation) > trace > call.

    Created explicitly (web UI / API); the ingest never creates one.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)  # a label for people
    # The identifier the SDK, the addresses and the S3 keys use: generated from the name when the
    # project is created (see app/slugs.py), never changed afterwards.
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_volumes_project_name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default="{}", default=dict
    )

    project: Mapped[Project] = relationship(lazy="joined")


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        UniqueConstraint("trace_id", "span_id", name="uq_llm_calls_trace_span"),
        Index("ix_llm_calls_volume_started", "volume_id", "started_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id", ondelete="CASCADE"))
    trace_id: Mapped[str] = mapped_column(String(32))
    span_id: Mapped[str] = mapped_column(String(16))

    # names chosen by the application (aicontrol.trace / aicontrol.step); the UI groups the calls
    # of a trace_id into a tree and labels them with these
    trace_name: Mapped[str | None] = mapped_column(String(255))
    step_name: Mapped[str | None] = mapped_column(String(255))

    # model / provider
    operation: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    request_model: Mapped[str | None] = mapped_column(String(255))
    response_model: Mapped[str | None] = mapped_column(String(255))
    api_base: Mapped[str | None] = mapped_column(Text)
    response_id: Mapped[str | None] = mapped_column(String(255))

    # timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    is_streaming: Mapped[bool | None]

    # tokens
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)

    # outcome
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error_type: Mapped[str | None] = mapped_column(String(255))
    finish_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    # request settings
    temperature: Mapped[float | None] = mapped_column(Float)
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    top_p: Mapped[float | None] = mapped_column(Float)

    # tools
    tools_offered: Mapped[int | None] = mapped_column(Integer)
    tool_calls_made: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    # display + pointer to the full trace in S3
    preview: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    trace_key: Mapped[str] = mapped_column(Text)
    trace_size_bytes: Mapped[int | None] = mapped_column(Integer)

    # reserved for authentication
    user_id: Mapped[str | None] = mapped_column(String(255))

    volume: Mapped[Volume] = relationship(lazy="joined")
