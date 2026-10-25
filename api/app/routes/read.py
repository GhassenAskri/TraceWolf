"""REST API for the web UI: projects, their volumes and calls, one call, and volume exports."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository as repo
from app.deps import get_session, get_store
from app.schemas import (
    CallDetail,
    CallPageOut,
    CallSummary,
    ConversationPageOut,
    ProjectCreate,
    ProjectOut,
    VolumeExportOut,
    VolumeOut,
)
from app.services import calls as svc
from app.storage.base import TraceNotFoundError, TraceStore
from app.views import format_transcript

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["read"])

Session = Annotated[AsyncSession, Depends(get_session)]
Store = Annotated[TraceStore, Depends(get_store)]


@router.get("/projects")
async def list_projects(session: Session) -> list[ProjectOut]:
    """Every project with its volume and call counts, alphabetically."""
    return [ProjectOut.of(p) for p in await repo.list_projects(session)]


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreate, session: Session) -> ProjectOut:
    """Create a project from its name. The API generates its slug (``Support Desk`` →
    ``support-desk``, numbered if taken): that is what the SDK and the addresses use. 409 if a
    project already has this name (names are case-sensitive).

    Projects are only created here: calls sent by the SDK for a project that does not exist are
    rejected.
    """
    try:
        project = await repo.create_project(session, body.name)
        await session.commit()
    except repo.ProjectExistsError as exc:
        await session.rollback()
        raise HTTPException(409, f"Project {body.name!r} already exists") from exc
    summary = await repo.get_project_summary(session, project.slug)
    assert summary is not None  # just created
    return ProjectOut.of(summary)


@router.get("/projects/{project}")
async def get_project(project: str, session: Session) -> ProjectOut:
    """One project, by its slug."""
    summary = await repo.get_project_summary(session, project)
    if summary is None:
        raise HTTPException(404, _no_project(project))
    return ProjectOut.of(summary)


@router.get("/projects/{project}/volumes")
async def list_volumes(project: str, session: Session) -> list[VolumeOut]:
    await _require_project(session, project)
    return [VolumeOut.of(v) for v in await repo.list_volumes(session, project)]


@router.get("/projects/{project}/conversations")
async def list_conversations(
    project: str,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=500)] = 30,
) -> ConversationPageOut:
    """The `limit` most recently active conversations (volumes) of the project, newest activity
    first, with their call counts. `has_more` says whether older ones exist; ask for a larger
    `limit` to see them."""
    await _require_project(session, project)
    page = await repo.list_recent_volumes(session, project, limit)
    return ConversationPageOut(items=[VolumeOut.of(v) for v in page.items], has_more=page.has_more)


# `{name:path}` so volume names containing "/" work.
@router.get("/projects/{project}/volumes/{name:path}/calls")
async def list_calls(
    project: str,
    name: str,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: str | None = None,
) -> CallPageOut:
    """Calls of a volume, oldest first. Pass `next_cursor` back as `cursor` for the next page
    (or to poll for new calls)."""
    await _require_volume(session, project, name)
    try:
        page = await repo.list_calls(session, project, name, limit=limit, cursor=cursor)
    except repo.InvalidCursorError as exc:
        raise HTTPException(400, str(exc)) from exc
    return CallPageOut(
        project=project,
        volume=name,
        items=[CallSummary.of(c) for c in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/calls/{call_id}")
async def get_call(call_id: int, session: Session, store: Store) -> CallDetail:
    call = await repo.get_call(session, call_id)
    if call is None:
        raise HTTPException(404, f"Call {call_id} not found")
    summary = CallSummary.of(call).model_dump()
    try:
        trace = await svc.load_trace(store, call)
        return CallDetail(**summary, trace=trace, trace_key=call.trace_key)
    except TraceNotFoundError:
        logger.error("Trace object %s of call %s is missing", call.trace_key, call.id)
        return CallDetail(
            **summary,
            trace=None,
            trace_error=f"Trace object {call.trace_key} not found in storage",
            trace_key=call.trace_key,
        )


@router.get("/projects/{project}/volumes/{name:path}/export", response_model=None)
async def export_volume(
    project: str,
    name: str,
    session: Session,
    store: Store,
    until: datetime | None = None,
    format: Literal["json", "text"] = "json",
) -> VolumeExportOut | PlainTextResponse:
    """Every call of the volume up to `until` (default: now) with its full trace, oldest first.

    `snapshot` lists exactly which calls were included. `format=text` returns a transcript.
    """
    await _require_volume(session, project, name)
    cutoff = _utc(until) or datetime.now(UTC)
    try:
        export = await svc.export_volume(session, store, project, name, cutoff)
    except TraceNotFoundError as exc:
        raise HTTPException(502, f"Export incomplete: trace object {exc} not found") from exc
    if format == "text":
        return PlainTextResponse(format_transcript(project, name, cutoff.isoformat(), export.calls))
    return VolumeExportOut(
        project=project, volume=name, until=cutoff, snapshot=export.snapshot, calls=export.calls
    )


def _no_project(project: str) -> str:
    return f"Project {project!r} not found"


async def _require_project(session: AsyncSession, project: str) -> None:
    if await repo.get_project(session, project) is None:
        raise HTTPException(404, _no_project(project))


async def _require_volume(session: AsyncSession, project: str, name: str) -> None:
    if await repo.get_volume(session, project, name) is None:
        await _require_project(session, project)  # a missing project is the clearer 404
        raise HTTPException(404, f"Volume {name!r} not found in project {project!r}")


def _utc(value: datetime | None) -> datetime | None:
    """Query datetimes without a timezone are taken as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
