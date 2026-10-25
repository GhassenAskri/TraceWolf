"""Data access for the Postgres index (projects, volumes and llm_calls)."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LlmCall, Project, Volume
from app.slugs import MAX_SLUG_LENGTH, next_free_slug, slugify


@dataclass(frozen=True)
class NewCall:
    """Index row for one LLM call, produced by the ingest mapper.

    ``project`` is the slug of the project the call was sent to.
    """

    project: str
    volume: str
    trace_id: str
    span_id: str
    started_at: datetime
    trace_key: str
    trace_name: str | None = None
    step_name: str | None = None
    operation: str | None = None
    provider: str | None = None
    request_model: str | None = None
    response_model: str | None = None
    api_base: str | None = None
    response_id: str | None = None
    ended_at: datetime | None = None
    latency_ms: int | None = None
    is_streaming: bool | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    status: str = "ok"
    error_type: str | None = None
    finish_reasons: list[str] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    tools_offered: int | None = None
    tool_calls_made: list[str] | None = None
    preview: list[dict[str, Any]] | None = None
    trace_size_bytes: int | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class ProjectSummary:
    name: str
    slug: str
    volume_count: int
    call_count: int
    created_at: datetime
    last_activity_at: datetime | None


@dataclass(frozen=True)
class VolumeSummary:
    name: str
    call_count: int
    created_at: datetime
    last_activity_at: datetime | None


@dataclass(frozen=True)
class VolumePage:
    items: list[VolumeSummary]
    has_more: bool


@dataclass(frozen=True)
class CallPage:
    items: list[LlmCall]
    next_cursor: str | None
    has_more: bool


class InvalidCursorError(ValueError):
    pass


class ProjectExistsError(ValueError):
    """A project with that name already exists."""


class UnknownProjectError(LookupError):
    """Calls refer to projects that do not exist (projects are created explicitly)."""

    def __init__(self, slugs: Collection[str]) -> None:
        self.names = sorted(slugs)
        super().__init__(f"Unknown project(s): {', '.join(self.names)}")


def _project_id(slug: str):
    """The id of the project with this slug, as a subquery (no row matches an unknown slug)."""
    return select(Project.id).where(Project.slug == slug).scalar_subquery()


# --- projects ---------------------------------------------------------------------------------


_SLUG_ATTEMPTS = 5


async def create_project(session: AsyncSession, name: str) -> Project:
    """Create a project and generate its slug from the name (``Support Desk`` → ``support-desk``,
    then ``support-desk-2``... when the slug is taken).

    Raises ``ProjectExistsError`` if the name is taken (names are case-sensitive). Two requests
    that want the same slug at the same moment both succeed: the one that lost the race takes the
    next number. The caller owns the transaction (commit/rollback).
    """
    base = slugify(name)
    stem = base[: MAX_SLUG_LENGTH - 8]  # room for a number: every candidate starts with the stem
    for _ in range(_SLUG_ATTEMPTS):
        taken = (
            await session.execute(select(Project.slug).where(Project.slug.like(f"{stem}%")))
        ).scalars()
        stmt = (
            insert(Project)
            .values(name=name, slug=next_free_slug(base, set(taken)))
            .on_conflict_do_nothing()  # either unique constraint: the name or the slug
            .returning(Project)
        )
        project = (await session.execute(stmt)).scalar_one_or_none()
        if project is not None:
            return project
        if await get_project_by_name(session, name) is not None:
            raise ProjectExistsError(name)
        # not the name: another request took this slug a moment ago; try the next number
    raise RuntimeError(f"Could not find a free slug for {name!r}")


async def get_project(session: AsyncSession, slug: str) -> Project | None:
    """The project with this slug (the name is only a label, not an identifier)."""
    return (await session.execute(select(Project).where(Project.slug == slug))).scalar_one_or_none()


async def get_project_by_name(session: AsyncSession, name: str) -> Project | None:
    return (await session.execute(select(Project).where(Project.name == name))).scalar_one_or_none()


def _project_summaries():
    return (
        select(
            Project.name,
            Project.slug,
            func.count(Volume.id.distinct()),
            func.count(LlmCall.id),
            Project.created_at,
            func.max(Volume.last_activity_at),
        )
        .outerjoin(Volume, Volume.project_id == Project.id)
        .outerjoin(LlmCall, LlmCall.volume_id == Volume.id)
        .group_by(Project.id)
    )


async def list_projects(session: AsyncSession) -> list[ProjectSummary]:
    """Every project with its volume and call counts, alphabetically (case-insensitive)."""
    stmt = _project_summaries().order_by(func.lower(Project.name), Project.name)
    return [ProjectSummary(*row) for row in (await session.execute(stmt)).all()]


async def get_project_summary(session: AsyncSession, slug: str) -> ProjectSummary | None:
    row = (await session.execute(_project_summaries().where(Project.slug == slug))).first()
    return ProjectSummary(*row) if row else None


async def existing_project_slugs(session: AsyncSession, slugs: Collection[str]) -> set[str]:
    """Which of ``slugs`` are projects."""
    if not slugs:
        return set()
    stmt = select(Project.slug).where(Project.slug.in_(slugs))
    return set((await session.execute(stmt)).scalars().all())


# --- volumes and calls ------------------------------------------------------------------------


async def upsert_volume(
    session: AsyncSession, project_id: int, name: str, activity_at: datetime
) -> int:
    """Create the volume if needed, move `last_activity_at` forward, and return its id."""
    stmt = insert(Volume).values(project_id=project_id, name=name, last_activity_at=activity_at)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Volume.project_id, Volume.name],
        set_={
            "last_activity_at": func.greatest(
                Volume.last_activity_at, stmt.excluded.last_activity_at
            )
        },
    ).returning(Volume.id)
    return (await session.execute(stmt)).scalar_one()


async def insert_calls(session: AsyncSession, calls: list[NewCall]) -> int:
    """Insert index rows, creating volumes on the fly inside their (existing) project.

    Raises ``UnknownProjectError`` before writing anything if a call names a project (by slug)
    that does not exist. Already-stored spans are ignored. Returns the number of new rows. The
    caller owns the transaction (commit/rollback).
    """
    if not calls:
        return 0

    slugs = {c.project for c in calls}
    stmt = select(Project.slug, Project.id).where(Project.slug.in_(slugs))
    project_ids = {slug: id_ for slug, id_ in (await session.execute(stmt)).all()}
    if missing := slugs - project_ids.keys():
        raise UnknownProjectError(missing)

    volume_ids: dict[tuple[str, str], int] = {}
    for project, name in sorted({(c.project, c.volume) for c in calls}):
        latest = max(c.started_at for c in calls if (c.project, c.volume) == (project, name))
        volume_ids[project, name] = await upsert_volume(session, project_ids[project], name, latest)

    rows = []
    for call in calls:
        row = {k: v for k, v in call.__dict__.items() if k not in ("project", "volume")}
        row["volume_id"] = volume_ids[call.project, call.volume]
        rows.append(row)

    stmt = (
        insert(LlmCall)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_llm_calls_trace_span")
        .returning(LlmCall.id)
    )
    return len((await session.execute(stmt)).all())


async def list_volumes(session: AsyncSession, project: str) -> list[VolumeSummary]:
    """All volumes of a project with their call counts, most recently active first."""
    stmt = (
        select(Volume.name, func.count(LlmCall.id), Volume.created_at, Volume.last_activity_at)
        .outerjoin(LlmCall, LlmCall.volume_id == Volume.id)
        .where(Volume.project_id == _project_id(project))
        .group_by(Volume.id)
        .order_by(Volume.last_activity_at.desc().nulls_last(), Volume.name)
    )
    return [VolumeSummary(*row) for row in (await session.execute(stmt)).all()]


async def list_recent_volumes(session: AsyncSession, project: str, limit: int) -> VolumePage:
    """The `limit` most recent volumes of a project with their call counts, in `list_volumes` order.

    Calls are counted only for the returned volumes, so it stays cheap however many calls are
    stored (the sidebar polls this).
    """
    stmt = (
        select(Volume)
        .where(Volume.project_id == _project_id(project))
        .order_by(Volume.last_activity_at.desc().nulls_last(), Volume.name)
        .limit(limit + 1)
    )
    fetched = list((await session.execute(stmt)).scalars().all())
    volumes = fetched[:limit]

    counts: dict[int, int] = {}
    if volumes:
        count_stmt = (
            select(LlmCall.volume_id, func.count(LlmCall.id))
            .where(LlmCall.volume_id.in_([v.id for v in volumes]))
            .group_by(LlmCall.volume_id)
        )
        counts = {volume_id: n for volume_id, n in (await session.execute(count_stmt)).all()}

    return VolumePage(
        items=[
            VolumeSummary(v.name, counts.get(v.id, 0), v.created_at, v.last_activity_at)
            for v in volumes
        ],
        has_more=len(fetched) > limit,
    )


async def get_volume(session: AsyncSession, project: str, name: str) -> Volume | None:
    stmt = select(Volume).where(Volume.project_id == _project_id(project), Volume.name == name)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_calls(
    session: AsyncSession,
    project: str,
    volume: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> CallPage:
    """Calls of a project's volume in chronological order.

    Keyset pagination on (started_at, id): pass `next_cursor` back to get the following page,
    which also returns calls that arrived after the previous page (used for live refresh).
    """
    stmt = (
        select(LlmCall)
        .join(Volume, LlmCall.volume_id == Volume.id)
        .where(Volume.project_id == _project_id(project), Volume.name == volume)
        .order_by(LlmCall.started_at, LlmCall.id)
        .limit(limit + 1)
    )
    if cursor is not None:
        after_started_at, after_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(LlmCall.started_at, LlmCall.id) > (after_started_at, after_id))

    rows = list((await session.execute(stmt)).scalars().all())
    items = rows[:limit]
    next_cursor = encode_cursor(items[-1]) if items else cursor
    return CallPage(items=items, next_cursor=next_cursor, has_more=len(rows) > limit)


async def get_call(session: AsyncSession, call_id: int) -> LlmCall | None:
    return await session.get(LlmCall, call_id)


async def list_calls_until(
    session: AsyncSession, project: str, volume: str, until: datetime
) -> list[LlmCall]:
    """Every call of a project's volume that started at or before `until`, oldest first."""
    stmt = (
        select(LlmCall)
        .join(Volume, LlmCall.volume_id == Volume.id)
        .where(
            Volume.project_id == _project_id(project),
            Volume.name == volume,
            LlmCall.started_at <= until,
        )
        .order_by(LlmCall.started_at, LlmCall.id)
    )
    return list((await session.execute(stmt)).scalars().all())


def encode_cursor(call: LlmCall) -> str:
    raw = f"{call.started_at.isoformat()}|{call.id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        started_at, call_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(started_at), int(call_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursorError(f"Invalid cursor: {cursor!r}") from exc
