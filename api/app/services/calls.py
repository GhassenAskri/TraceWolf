"""Storing and reading LLM calls across the two stores: full trace in S3, index in Postgres."""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import repository as repo
from app.models import LlmCall
from app.repository import NewCall
from app.storage.base import TraceStore, build_trace_key


@dataclass(frozen=True)
class CallToStore:
    """One LLM call as produced by the ingest mapper: index row + full trace document.

    ``row.trace_key`` is ignored; it is derived from the row.
    """

    row: NewCall
    trace: dict[str, Any]


@dataclass(frozen=True)
class VolumeExport:
    project: str
    volume: str
    until: datetime
    calls: list[dict[str, Any]]
    snapshot: dict[str, Any]


async def store_calls(session: AsyncSession, store: TraceStore, calls: list[CallToStore]) -> int:
    """Write every trace to S3 first, then the index rows in one transaction.

    If any S3 write fails, nothing is written to Postgres and the error propagates (the ingest
    endpoint then answers 5xx so the exporter retries). A crash between the two steps can only
    leave orphan objects, which a retry overwrites because keys are deterministic.
    Returns the number of new index rows (retried spans are not counted twice).
    """
    if not calls:
        return 0
    keys = [
        build_trace_key(
            c.row.project, c.row.volume, c.row.started_at, c.row.trace_id, c.row.span_id
        )
        for c in calls
    ]
    sizes = await asyncio.gather(*(store.put(k, c.trace) for k, c in zip(keys, calls, strict=True)))
    rows = [
        dataclasses.replace(c.row, trace_key=key, trace_size_bytes=size)
        for c, key, size in zip(calls, keys, sizes, strict=True)
    ]
    try:
        inserted = await repo.insert_calls(session, rows)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return inserted


async def load_trace(store: TraceStore, call: LlmCall) -> dict[str, Any]:
    return await store.get(call.trace_key)


async def export_volume(
    session: AsyncSession, store: TraceStore, project: str, volume: str, until: datetime
) -> VolumeExport:
    """Every call of the project's volume up to ``until`` with its full trace, oldest first.

    ``snapshot`` records exactly which calls were included, so an evaluation run can later say
    what it evaluated even though the volume keeps growing.
    """
    calls = await repo.list_calls_until(session, project, volume, until)
    traces = await store.get_many([c.trace_key for c in calls])
    return VolumeExport(
        project=project,
        volume=volume,
        until=until,
        calls=[{"id": c.id, **t} for c, t in zip(calls, traces, strict=True)],
        snapshot={
            "project": project,
            "volume": volume,
            "until": until.isoformat(),
            "call_count": len(calls),
            "call_ids": [c.id for c in calls],
        },
    )
