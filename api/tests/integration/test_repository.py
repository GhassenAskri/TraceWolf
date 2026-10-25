import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, text

from app import repository as repo
from app.repository import NewCall
from tests.spans import PROJECT

T0 = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def make_call(
    volume="alice-chat-42", span="0000000000000001", at=T0, project=PROJECT, **overrides
) -> NewCall:
    fields = {
        "project": project,
        "volume": volume,
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "span_id": span,
        "started_at": at,
        "ended_at": at + timedelta(milliseconds=820),
        "trace_key": f"projects/{project}/volumes/{volume}/{at:%Y/%m/%d}/{span}.json",
        "request_model": "gpt-4o-mini",
        "input_tokens": 45,
        "output_tokens": 8,
    }
    return NewCall(**{**fields, **overrides})


def spans(n: int, start: datetime = T0, step: timedelta = timedelta(seconds=1), **kw):
    return [make_call(span=f"{i + 1:016x}", at=start + i * step, **kw) for i in range(n)]


async def test_insert_stores_all_monitoring_columns(session):
    call = make_call(
        operation="chat",
        provider="openai",
        response_model="gpt-4o-mini-2024-07-18",
        api_base="https://api.openai.com/v1/",
        response_id="chatcmpl-1",
        latency_ms=820,
        is_streaming=True,
        total_tokens=53,
        cached_input_tokens=10,
        reasoning_tokens=3,
        status="error",
        error_type="RateLimitError",
        finish_reasons=["tool_call"],
        temperature=0.2,
        max_tokens=100,
        top_p=0.9,
        tools_offered=2,
        tool_calls_made=["get_weather"],
        preview=[{"role": "user", "content": "hi"}],
        trace_size_bytes=2048,
        user_id=None,
    )

    assert await repo.insert_calls(session, [call]) == 1
    await session.commit()

    (stored,) = (await repo.list_calls(session, PROJECT, "alice-chat-42")).items
    for name, value in call.__dict__.items():
        if name == "volume":
            assert stored.volume.name == value
        elif name == "project":
            assert stored.volume.project.name == value
        else:
            assert getattr(stored, name) == value, name


async def test_duplicate_trace_and_span_is_ignored(session):
    assert await repo.insert_calls(session, [make_call()]) == 1
    assert await repo.insert_calls(session, [make_call(), make_call(span="0000000000000002")]) == 1
    await session.commit()

    assert len((await repo.list_calls(session, PROJECT, "alice-chat-42")).items) == 2


async def test_volume_is_created_on_first_call_and_activity_moves_forward(session):
    await repo.insert_calls(session, [make_call(at=T0)])
    await repo.insert_calls(
        session, [make_call(span="0000000000000002", at=T0 - timedelta(hours=1))]
    )
    await repo.insert_calls(
        session, [make_call(span="0000000000000003", at=T0 + timedelta(hours=1))]
    )
    await session.commit()

    volume = await repo.get_volume(session, PROJECT, "alice-chat-42")
    assert volume is not None
    assert volume.last_activity_at == T0 + timedelta(hours=1)


async def test_list_volumes_counts_calls_most_recent_first(session):
    await repo.insert_calls(session, spans(3, volume="old", start=T0))
    await repo.insert_calls(
        session, [make_call(volume="new", span="00000000000000ff", at=T0 + timedelta(days=1))]
    )
    await session.commit()

    volumes = await repo.list_volumes(session, PROJECT)

    assert [(v.name, v.call_count) for v in volumes] == [("new", 1), ("old", 3)]


async def seed_volumes(session):
    """old (3 calls, T0), mid (2 calls, T0 + 12h), new (1 call, T0 + 1 day)."""
    # (trace_id, span_id) is unique across volumes, so each volume needs its own span ids.
    await repo.insert_calls(session, spans(3, volume="old", start=T0))
    await repo.insert_calls(
        session,
        [
            make_call(volume="mid", span=f"{0xB0 + i:016x}", at=T0 + timedelta(hours=12, seconds=i))
            for i in range(2)
        ],
    )
    await repo.insert_calls(
        session, [make_call(volume="new", span="00000000000000ff", at=T0 + timedelta(days=1))]
    )
    await session.commit()


async def test_list_recent_volumes_most_recent_first_with_counts(session):
    await seed_volumes(session)

    page = await repo.list_recent_volumes(session, PROJECT, limit=30)

    assert [(v.name, v.call_count) for v in page.items] == [("new", 1), ("mid", 2), ("old", 3)]
    assert page.has_more is False


async def test_list_recent_volumes_has_more_only_when_volumes_remain(session):
    await seed_volumes(session)

    exact = await repo.list_recent_volumes(session, PROJECT, limit=3)
    cut = await repo.list_recent_volumes(session, PROJECT, limit=2)
    one = await repo.list_recent_volumes(session, PROJECT, limit=1)

    assert (len(exact.items), exact.has_more) == (3, False)
    assert ([v.name for v in cut.items], cut.has_more) == (["new", "mid"], True)
    assert ([(v.name, v.call_count) for v in one.items], one.has_more) == ([("new", 1)], True)


async def test_list_recent_volumes_empty_database(session):
    page = await repo.list_recent_volumes(session, PROJECT, limit=30)

    assert page.items == []
    assert page.has_more is False


async def test_list_recent_volumes_matches_list_volumes(session):
    await seed_volumes(session)

    page = await repo.list_recent_volumes(session, PROJECT, limit=30)

    assert page.items == await repo.list_volumes(session, PROJECT)


async def test_list_recent_volumes_counts_only_the_returned_volumes(session):
    await seed_volumes(session)
    statements: list[str] = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    engine = session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        await repo.list_recent_volumes(session, PROJECT, limit=1)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert len(statements) == 2
    assert "volume_id in" in statements[1].lower()  # not a count over every call


async def test_calls_are_scoped_to_their_volume(session):
    await repo.insert_calls(
        session, spans(2, volume="a") + [make_call(volume="b", span="00000000000000bb")]
    )
    await session.commit()

    assert len((await repo.list_calls(session, PROJECT, "a")).items) == 2
    assert len((await repo.list_calls(session, PROJECT, "b")).items) == 1
    assert (await repo.list_calls(session, PROJECT, "missing")).items == []


async def test_cursor_pagination_is_stable_and_chronological(session):
    same_time = [make_call(span=f"{0xA0 + i:016x}", at=T0) for i in range(3)]
    await repo.insert_calls(session, spans(4, start=T0 + timedelta(seconds=1)) + same_time)
    await session.commit()

    seen, cursor = [], None
    while True:
        page = await repo.list_calls(session, PROJECT, "alice-chat-42", limit=2, cursor=cursor)
        seen += page.items
        cursor = page.next_cursor
        if not page.has_more:
            break

    assert len(seen) == 7
    assert len({c.id for c in seen}) == 7
    keys = [(c.started_at, c.id) for c in seen]
    assert keys == sorted(keys)


async def test_cursor_returns_calls_that_arrive_later(session):
    await repo.insert_calls(session, spans(2))
    await session.commit()
    first = await repo.list_calls(session, PROJECT, "alice-chat-42")

    await repo.insert_calls(
        session, [make_call(span="00000000000000aa", at=T0 + timedelta(minutes=5))]
    )
    await session.commit()
    later = await repo.list_calls(session, PROJECT, "alice-chat-42", cursor=first.next_cursor)

    assert [c.span_id for c in later.items] == ["00000000000000aa"]


async def test_empty_page_keeps_the_cursor(session):
    await repo.insert_calls(session, spans(1))
    await session.commit()
    first = await repo.list_calls(session, PROJECT, "alice-chat-42")

    empty = await repo.list_calls(session, PROJECT, "alice-chat-42", cursor=first.next_cursor)

    assert empty.items == []
    assert empty.next_cursor == first.next_cursor


async def test_invalid_cursor_is_rejected(session):
    with pytest.raises(repo.InvalidCursorError):
        await repo.list_calls(session, PROJECT, "alice-chat-42", cursor="not-a-cursor")


async def test_get_call(session):
    await repo.insert_calls(session, [make_call()])
    await session.commit()
    (call,) = (await repo.list_calls(session, PROJECT, "alice-chat-42")).items

    assert (await repo.get_call(session, call.id)).span_id == call.span_id
    assert await repo.get_call(session, 999_999) is None


async def test_list_calls_until_is_inclusive_and_ordered(session):
    await repo.insert_calls(session, list(reversed(spans(4, step=timedelta(minutes=1)))))
    await session.commit()

    calls = await repo.list_calls_until(
        session, PROJECT, "alice-chat-42", T0 + timedelta(minutes=2)
    )

    assert [c.started_at for c in calls] == [T0 + timedelta(minutes=i) for i in range(3)]


# --- projects ------------------------------------------------------------------------------------


async def test_create_and_get_a_project(session):
    project = await repo.create_project(session, "My Project")
    await session.commit()

    found = await repo.get_project(session, "my-project")  # by slug

    assert found is not None and found.id == project.id
    assert (found.name, found.slug) == ("My Project", "my-project")
    assert found.created_at is not None
    assert await repo.get_project(session, "My Project") is None  # the name is not an identifier
    assert await repo.get_project(session, "nope") is None


async def test_a_duplicate_name_is_refused_and_names_are_case_sensitive(session):
    await repo.create_project(session, "My Project")
    await session.commit()

    with pytest.raises(repo.ProjectExistsError):
        await repo.create_project(session, "My Project")
    other_case = await repo.create_project(session, "my project")  # a different name
    await session.commit()

    assert other_case.slug == "my-project-2"
    assert {p.name for p in await repo.list_projects(session)} == {
        PROJECT,
        "My Project",
        "my project",
    }


async def test_the_slug_is_generated_from_the_name_and_made_unique(session):
    names = ["Support Desk", "support desk", "Support-Desk", "Café Bot", "日本語", "!!!"]

    projects = [await repo.create_project(session, name) for name in names]
    await session.commit()

    assert [p.slug for p in projects] == [
        "support-desk",
        "support-desk-2",
        "support-desk-3",
        "cafe-bot",
        "project",
        "project-2",
    ]


async def test_a_slug_that_was_freed_by_a_gap_is_reused_smallest_first(session):
    for name in ["Foo", "foo!", "foo?"]:  # foo, foo-2, foo-3
        await repo.create_project(session, name)
    await session.commit()
    await session.execute(text("DELETE FROM projects WHERE slug = 'foo-2'"))
    await session.commit()

    assert (await repo.create_project(session, "FOO")).slug == "foo-2"


async def test_two_requests_creating_the_same_slug_at_once_both_succeed(session_factory):
    async def create(name):
        async with session_factory() as session:
            project = await repo.create_project(session, name)
            await session.commit()
            return project.slug

    slugs = await asyncio.gather(*(create(n) for n in ["Race Name", "race name", "RACE NAME"]))

    assert sorted(slugs) == ["race-name", "race-name-2", "race-name-3"]


async def test_two_requests_creating_the_same_name_at_once_only_one_wins(session_factory):
    async def create():
        async with session_factory() as session:
            try:
                project = await repo.create_project(session, "Same Name")
                await session.commit()
                return project.slug
            except repo.ProjectExistsError:
                await session.rollback()
                return "exists"

    results = await asyncio.gather(create(), create(), create())

    assert sorted(results) == ["exists", "exists", "same-name"]


async def test_list_projects_is_alphabetical_with_counts_and_last_activity(session):
    await repo.create_project(session, "beta")
    await repo.create_project(session, "Alpha")
    await repo.insert_calls(session, spans(3, volume="v1", project="beta"))
    await repo.insert_calls(
        session,
        [
            make_call(
                volume="v2", span="00000000000000a1", at=T0 + timedelta(days=1), project="beta"
            )
        ],
    )
    await session.commit()

    projects = await repo.list_projects(session)

    assert [p.name for p in projects] == ["Alpha", "beta", PROJECT]  # case-insensitive order
    by_name = {p.name: p for p in projects}
    assert [by_name[n].slug for n in ("Alpha", "beta")] == ["alpha", "beta"]
    assert (by_name["beta"].volume_count, by_name["beta"].call_count) == (2, 4)
    assert by_name["beta"].last_activity_at == T0 + timedelta(days=1)
    assert (by_name["Alpha"].volume_count, by_name["Alpha"].call_count) == (0, 0)
    assert by_name["Alpha"].last_activity_at is None


async def test_existing_project_slugs(session):
    await repo.create_project(session, "A")
    await session.commit()

    assert await repo.existing_project_slugs(session, {"a", PROJECT, "missing"}) == {"a", PROJECT}
    assert await repo.existing_project_slugs(session, {"A"}) == set()  # a name is not a slug
    assert await repo.existing_project_slugs(session, set()) == set()


async def test_get_project_summary(session):
    await repo.insert_calls(session, spans(2, volume="v1"))
    await session.commit()

    summary = await repo.get_project_summary(session, PROJECT)

    assert (summary.name, summary.slug) == (PROJECT, PROJECT)
    assert (summary.volume_count, summary.call_count) == (1, 2)
    assert summary == next(p for p in await repo.list_projects(session) if p.name == PROJECT)
    assert await repo.get_project_summary(session, "missing") is None


# --- the same volume name in two projects --------------------------------------------------------


async def seed_two_projects(session):
    """Both projects have a volume called "chat" (3 calls in "one", 2 in "two")."""
    await repo.create_project(session, "one")
    await repo.create_project(session, "two")
    await repo.insert_calls(session, spans(3, volume="chat", project="one"))
    await repo.insert_calls(
        session,
        [
            make_call(
                volume="chat", span=f"{0xC0 + i:016x}", at=T0 + timedelta(seconds=i), project="two"
            )
            for i in range(2)
        ],
    )
    await session.commit()


async def test_a_volume_name_can_exist_in_several_projects(session):
    await seed_two_projects(session)

    assert len((await repo.list_calls(session, "one", "chat")).items) == 3
    assert len((await repo.list_calls(session, "two", "chat")).items) == 2
    assert (await repo.get_volume(session, "one", "chat")).project.name == "one"
    assert (await repo.get_volume(session, "two", "chat")).project.name == "two"
    assert (await repo.get_volume(session, "one", "chat")).id != (
        await repo.get_volume(session, "two", "chat")
    ).id


async def test_a_project_never_sees_another_projects_calls(session):
    await seed_two_projects(session)

    assert [(v.name, v.call_count) for v in await repo.list_volumes(session, "one")] == [
        ("chat", 3)
    ]
    assert [(v.name, v.call_count) for v in await repo.list_volumes(session, "two")] == [
        ("chat", 2)
    ]
    assert (await repo.list_recent_volumes(session, "two", limit=30)).items[0].call_count == 2
    assert (await repo.list_calls(session, "two", "only-in-one")).items == []
    assert await repo.list_volumes(session, PROJECT) == []


async def test_pagination_and_export_cutoff_are_per_project(session):
    await seed_two_projects(session)

    page = await repo.list_calls(session, "one", "chat", limit=2)
    rest = await repo.list_calls(session, "one", "chat", limit=2, cursor=page.next_cursor)
    until = await repo.list_calls_until(session, "two", "chat", T0 + timedelta(minutes=1))

    assert len(page.items) + len(rest.items) == 3 and page.has_more and not rest.has_more
    assert {c.volume.project.name for c in page.items + rest.items} == {"one"}
    assert len(until) == 2 and {c.volume.project.name for c in until} == {"two"}


async def test_unknown_volumes_and_projects_are_empty(session):
    assert await repo.get_volume(session, PROJECT, "missing") is None
    assert await repo.get_volume(session, "no-such-project", "chat") is None
    assert await repo.list_volumes(session, "no-such-project") == []
    assert (await repo.list_recent_volumes(session, "no-such-project", limit=5)).items == []
    assert (await repo.list_calls(session, "no-such-project", "chat")).items == []


# --- inserting needs an existing project ---------------------------------------------------------


async def test_inserting_calls_for_an_unknown_project_raises_and_writes_nothing(session):
    batch = [make_call(), make_call(span="0000000000000002", project="ghost")]

    with pytest.raises(repo.UnknownProjectError) as error:
        await repo.insert_calls(session, batch)
    await session.rollback()

    assert error.value.names == ["ghost"]
    assert await repo.list_volumes(session, PROJECT) == []  # the valid call was not stored either


async def test_one_batch_can_hold_several_projects(session):
    await repo.create_project(session, "other")
    await session.commit()

    inserted = await repo.insert_calls(
        session, [make_call(), make_call(span="0000000000000002", project="other")]
    )
    await session.commit()

    assert inserted == 2
    assert len((await repo.list_calls(session, PROJECT, "alice-chat-42")).items) == 1
    assert len((await repo.list_calls(session, "other", "alice-chat-42")).items) == 1
