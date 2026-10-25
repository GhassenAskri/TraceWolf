"""Request and response models of the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, StringConstraints

from app.models import LlmCall
from app.repository import ProjectSummary, VolumeSummary

# The name is only a label (the slug, generated from it, is the identifier): any text, trimmed,
# 1-255 characters.
ProjectName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class ProjectCreate(BaseModel):
    name: ProjectName


class ProjectOut(BaseModel):
    name: str
    slug: str
    volume_count: int
    call_count: int
    created_at: datetime
    last_activity_at: datetime | None

    @classmethod
    def of(cls, p: ProjectSummary) -> ProjectOut:
        return cls(
            name=p.name,
            slug=p.slug,
            volume_count=p.volume_count,
            call_count=p.call_count,
            created_at=p.created_at,
            last_activity_at=p.last_activity_at,
        )


class VolumeOut(BaseModel):
    name: str
    call_count: int
    created_at: datetime
    last_activity_at: datetime | None

    @classmethod
    def of(cls, v: VolumeSummary) -> VolumeOut:
        return cls(
            name=v.name,
            call_count=v.call_count,
            created_at=v.created_at,
            last_activity_at=v.last_activity_at,
        )


class ConversationPageOut(BaseModel):
    """The most recently active conversations (volumes) and whether older ones exist."""

    items: list[VolumeOut]
    has_more: bool


class Tokens(BaseModel):
    input: int | None
    output: int | None
    total: int | None
    cached_input: int | None
    reasoning: int | None


class CallSummary(BaseModel):
    """Index data of a call (Postgres only) + the new messages of the call."""

    id: int
    project: str
    volume: str
    trace_id: str
    span_id: str
    trace_name: str | None
    step_name: str | None
    operation: str | None
    provider: str | None
    request_model: str | None
    response_model: str | None
    api_base: str | None
    response_id: str | None
    started_at: datetime
    ended_at: datetime | None
    latency_ms: int | None
    is_streaming: bool | None
    tokens: Tokens
    status: str
    error_type: str | None
    finish_reasons: list[str] | None
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    tools_offered: int | None
    tool_calls_made: list[str] | None
    new_messages: list[dict[str, Any]]
    trace_size_bytes: int | None

    @classmethod
    def of(cls, c: LlmCall) -> CallSummary:
        return cls(
            id=c.id,
            project=c.volume.project.slug,
            volume=c.volume.name,
            trace_id=c.trace_id,
            span_id=c.span_id,
            trace_name=c.trace_name,
            step_name=c.step_name,
            operation=c.operation,
            provider=c.provider,
            request_model=c.request_model,
            response_model=c.response_model,
            api_base=c.api_base,
            response_id=c.response_id,
            started_at=c.started_at,
            ended_at=c.ended_at,
            latency_ms=c.latency_ms,
            is_streaming=c.is_streaming,
            tokens=Tokens(
                input=c.input_tokens,
                output=c.output_tokens,
                total=c.total_tokens,
                cached_input=c.cached_input_tokens,
                reasoning=c.reasoning_tokens,
            ),
            status=c.status,
            error_type=c.error_type,
            finish_reasons=c.finish_reasons,
            temperature=c.temperature,
            max_tokens=c.max_tokens,
            top_p=c.top_p,
            tools_offered=c.tools_offered,
            tool_calls_made=c.tool_calls_made,
            new_messages=c.preview or [],
            trace_size_bytes=c.trace_size_bytes,
        )


class CallPageOut(BaseModel):
    project: str
    volume: str
    items: list[CallSummary]
    next_cursor: str | None
    has_more: bool


class CallDetail(CallSummary):
    """A call with its full trace from S3 (`trace` is null if the object is missing)."""

    trace: dict[str, Any] | None
    trace_error: str | None = None
    trace_key: str  # where the full trace lives in S3


class VolumeExportOut(BaseModel):
    project: str
    volume: str
    until: datetime
    snapshot: dict[str, Any]
    calls: list[dict[str, Any]]
