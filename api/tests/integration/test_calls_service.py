from datetime import UTC, datetime, timedelta

import pytest

from app import repository as repo
from app.services import calls as svc
from app.storage.base import volume_prefix
from app.storage.memory import InMemoryTraceStore
from tests.integration.test_repository import make_call
from tests.spans import PROJECT

T0 = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def to_store(
    span: str, at: datetime = T0, volume: str = "alice-chat-42", project: str = PROJECT
) -> svc.CallToStore:
    row = make_call(volume=volume, span=span, at=at, project=project, trace_key="ignored")
    trace = {
        "project": project,
        "volume": volume,
        "span_id": span,
        "input_messages": [{"role": "user", "content": span}],
    }
    return svc.CallToStore(row=row, trace=trace)


class FailingStore(InMemoryTraceStore):
    async def put(self, key, document):
        raise ConnectionError("S3 is down")


async def test_store_calls_writes_objects_then_index_rows(session):
    store = InMemoryTraceStore()

    inserted = await svc.store_calls(session, store, [to_store("0000000000000001")])

    assert inserted == 1
    (call,) = (await repo.list_calls(session, PROJECT, "alice-chat-42")).items
    assert call.trace_key.startswith(f"projects/{PROJECT}/volumes/alice-chat-42/2026/09/24/")
    assert call.trace_key in store.objects
    assert call.trace_size_bytes == len(store.objects[call.trace_key])
    assert (await svc.load_trace(store, call))["span_id"] == "0000000000000001"


async def test_s3_failure_writes_no_index_row(session):
    with pytest.raises(ConnectionError):
        await svc.store_calls(session, FailingStore(), [to_store("0000000000000001")])

    assert await repo.list_volumes(session, PROJECT) == []


async def test_retried_batch_is_stored_once(session):
    store = InMemoryTraceStore()
    batch = [to_store("0000000000000001"), to_store("0000000000000002")]

    assert await svc.store_calls(session, store, batch) == 2
    assert await svc.store_calls(session, store, batch) == 0

    assert len(store.objects) == 2
    assert len((await repo.list_calls(session, PROJECT, "alice-chat-42")).items) == 2


async def test_store_and_export_against_real_s3(session, s3_store):
    batch = [to_store(f"{i + 1:016x}", at=T0 + timedelta(minutes=i)) for i in range(4)]
    batch.append(to_store("00000000000000bb", volume="other"))
    await svc.store_calls(session, s3_store, list(reversed(batch)))

    export = await svc.export_volume(
        session, s3_store, PROJECT, "alice-chat-42", T0 + timedelta(minutes=2)
    )

    assert [c["span_id"] for c in export.calls] == [f"{i + 1:016x}" for i in range(3)]
    assert export.snapshot["call_count"] == 3
    assert export.snapshot["call_ids"] == [c["id"] for c in export.calls]
    assert export.snapshot["until"] == (T0 + timedelta(minutes=2)).isoformat()
    assert export.snapshot["project"] == PROJECT and export.project == PROJECT
    assert len(await s3_store.list_prefix(volume_prefix(PROJECT, "alice-chat-42"))) == 4
    assert len(await s3_store.list_prefix(volume_prefix(PROJECT, "other"))) == 1


async def test_export_of_unknown_volume_is_empty(session, s3_store):
    export = await svc.export_volume(session, s3_store, PROJECT, "missing", T0)

    assert export.calls == []
    assert export.snapshot["call_ids"] == []


async def test_the_same_volume_name_in_two_projects_is_stored_and_exported_separately(
    session, s3_store
):
    await repo.create_project(session, "other")
    await session.commit()
    batch = [
        to_store("0000000000000001"),
        to_store("0000000000000002", project="other"),
    ]

    await svc.store_calls(session, s3_store, batch)
    mine = await svc.export_volume(session, s3_store, PROJECT, "alice-chat-42", T0)
    theirs = await svc.export_volume(session, s3_store, "other", "alice-chat-42", T0)

    assert [c["span_id"] for c in mine.calls] == ["0000000000000001"]
    assert [c["span_id"] for c in theirs.calls] == ["0000000000000002"]
    assert len(await s3_store.list_prefix(volume_prefix(PROJECT, "alice-chat-42"))) == 1
    assert len(await s3_store.list_prefix(volume_prefix("other", "alice-chat-42"))) == 1


async def test_store_calls_for_an_unknown_project_writes_no_index_row(session):
    with pytest.raises(repo.UnknownProjectError):
        await svc.store_calls(
            session, InMemoryTraceStore(), [to_store("0000000000000001", project="ghost")]
        )

    assert await repo.list_volumes(session, PROJECT) == []
