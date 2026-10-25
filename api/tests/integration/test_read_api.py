from datetime import UTC, datetime, timedelta

import aicontrol
import httpx2
import pytest

from app.main import create_app
from app.services import calls as svc
from app.storage.memory import InMemoryTraceStore
from app.views import new_messages
from tests import spans as s
from tests.integration.test_repository import make_call
from tests.spans import PROJECT

T0 = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
P = f"/api/projects/{PROJECT}"  # the project every integration test starts with
PROTOBUF = {"content-type": "application/x-protobuf"}


@pytest.fixture(scope="module")
def conversation():
    """A real tool-using conversation in one volume + a call in another volume."""
    return s.to_protobuf(
        s.capture(
            s.chat(volume="alice-chat-42", reply=s.TOOL_CALL_REPLY, tools=[s.WEATHER_TOOL]),
            s.chat(volume="alice-chat-42", messages=s.TOOL_ROUND_TRIP, tools=[s.WEATHER_TOOL]),
            s.chat(volume="team/support"),
        )
    )


@pytest.fixture
def store():
    return InMemoryTraceStore()


@pytest.fixture
async def client(session_factory, store, conversation):
    app = create_app(session_factory=session_factory, trace_store=store)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://api"
    ) as client:
        response = await client.post("/v1/traces", content=conversation, headers=PROTOBUF)
        assert response.status_code == 200
        yield client


async def seed_timed(session_factory, store, volume="timed", minutes=5, project=PROJECT):
    batch = []
    for i in range(minutes):
        inputs = [{"role": "user", "content": f"q{i}"}]
        outputs = [{"role": "assistant", "content": f"a{i}"}]
        row = make_call(
            volume=volume,
            span=f"{i + 1:016x}",
            at=T0 + timedelta(minutes=i),
            project=project,
            trace_key="",
            preview=new_messages(inputs, outputs),
        )
        trace = {
            "project": project,
            "volume": volume,
            "started_at": row.started_at.isoformat(),
            "status": "ok",
            "input_messages": inputs,
            "output_messages": outputs,
        }
        batch.append(svc.CallToStore(row=row, trace=trace))
    async with session_factory() as session:
        await svc.store_calls(session, store, batch)


# --- projects -----------------------------------------------------------------------------------


async def test_list_projects_with_counts(client):
    response = await client.get("/api/projects")

    assert response.status_code == 200
    (project,) = response.json()
    assert (project["name"], project["slug"]) == (PROJECT, PROJECT)
    assert (project["volume_count"], project["call_count"]) == (2, 3)
    assert project["created_at"] and project["last_activity_at"]


async def test_create_a_project_generates_its_slug(client):
    response = await client.post("/api/projects", json={"name": "  Support Desk  "})

    assert response.status_code == 201
    created = response.json()
    assert (created["name"], created["slug"]) == ("Support Desk", "support-desk")  # name trimmed
    assert (created["volume_count"], created["call_count"]) == (0, 0)
    assert created["last_activity_at"] is None
    names = [p["name"] for p in (await client.get("/api/projects")).json()]
    assert names == ["Support Desk", PROJECT]  # alphabetical by name, case-insensitive


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Café Bot", "cafe-bot"),
        ("a/b", "a-b"),
        ("日本語", "project"),
        ("Version 2.0", "version-2-0"),
    ],
)
async def test_the_slug_is_url_safe_whatever_the_name(client, name, slug):
    response = await client.post("/api/projects", json={"name": name})

    assert response.status_code == 201
    assert response.json()["slug"] == slug
    assert (await client.get(f"/api/projects/{slug}")).json()["name"] == name


async def test_names_that_give_the_same_slug_get_numbered_slugs(client):
    first = (await client.post("/api/projects", json={"name": "Support Desk"})).json()
    second = (await client.post("/api/projects", json={"name": "support desk"})).json()
    third = (await client.post("/api/projects", json={"name": "Support-Desk"})).json()

    assert [first["slug"], second["slug"], third["slug"]] == [
        "support-desk",
        "support-desk-2",
        "support-desk-3",
    ]


async def test_creating_a_duplicate_name_is_a_conflict(client):
    await client.post("/api/projects", json={"name": "My Project"})

    response = await client.post("/api/projects", json={"name": "My Project"})

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    assert len((await client.get("/api/projects")).json()) == 2  # nothing was created


@pytest.mark.parametrize("name", ["", "   ", "x" * 256])
async def test_invalid_project_names_are_refused(client, name):
    response = await client.post("/api/projects", json={"name": name})

    assert response.status_code == 422
    assert len((await client.get("/api/projects")).json()) == 1


async def test_a_project_name_is_required(client):
    assert (await client.post("/api/projects", json={})).status_code == 422
    assert (await client.post("/api/projects", json={"name": 3})).status_code == 422


async def test_a_project_is_addressed_by_its_slug_not_its_name(client):
    await client.post("/api/projects", json={"name": "My Project"})

    found = await client.get("/api/projects/my-project")
    by_name = await client.get("/api/projects/My%20Project")
    missing = await client.get("/api/projects/nope")

    assert found.status_code == 200
    assert (found.json()["name"], found.json()["slug"]) == ("My Project", "my-project")
    assert by_name.status_code == 404 and "My Project" in by_name.json()["detail"]
    assert missing.status_code == 404 and "nope" in missing.json()["detail"]


# --- the hierarchy: project > volume > calls -----------------------------------------------------


async def test_list_volumes(client):
    response = await client.get(f"{P}/volumes")

    assert response.status_code == 200
    volumes = {v["name"]: v for v in response.json()}
    assert volumes["alice-chat-42"]["call_count"] == 2
    assert volumes["team/support"]["call_count"] == 1
    assert volumes["alice-chat-42"]["last_activity_at"] is not None


async def test_list_conversations_is_scoped_to_the_project(client, session_factory, store):
    await client.post("/api/projects", json={"name": "other"})
    await seed_timed(session_factory, store, volume="elsewhere", project="other")

    mine = (await client.get(f"{P}/conversations")).json()
    theirs = (await client.get("/api/projects/other/conversations")).json()

    assert {v["name"] for v in mine["items"]} == {"alice-chat-42", "team/support"}
    assert [v["name"] for v in theirs["items"]] == ["elsewhere"]
    assert theirs["has_more"] is False


async def test_list_calls_returns_summaries_with_new_messages(client):
    response = await client.get(f"{P}/volumes/alice-chat-42/calls")

    assert response.status_code == 200
    page = response.json()
    assert page["project"] == PROJECT
    assert page["volume"] == "alice-chat-42"
    assert page["has_more"] is False
    first, second = page["items"]
    assert first["project"] == PROJECT
    assert "app_name" not in first
    assert first["tool_calls_made"] == ["get_weather"]
    assert first["finish_reasons"] == ["tool_call"]
    assert first["tokens"] == {
        "input": 45,
        "output": 8,
        "total": 53,
        "cached_input": 10,
        "reasoning": 3,
    }
    assert [m["role"] for m in first["new_messages"]] == ["system", "user", "assistant"]
    assert [m["role"] for m in second["new_messages"]] == ["tool", "assistant"]
    assert second["new_messages"][1]["content"] == "Sunny, 22°C"
    assert "trace" not in first


async def test_calls_of_a_trace_share_a_trace_id_and_carry_their_names(session_factory, store):
    summarize = s.traced(
        "Summarize this PDF",
        ("extract key points", s.chat()),
        ("write summary", s.chat()),
        ("translate to French", s.chat()),
    )

    def summarize_in_pdf_volume():
        with aicontrol.volume("pdf"):
            summarize()

    body = s.to_protobuf(s.capture(s.chat(volume="plain"), summarize_in_pdf_volume))
    app = create_app(session_factory=session_factory, trace_store=store)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://api"
    ) as client:
        posted = await client.post("/v1/traces", content=body, headers=PROTOBUF)
        assert posted.status_code == 200

        pdf = (await client.get(f"{P}/volumes/pdf/calls")).json()["items"]
        plain = (await client.get(f"{P}/volumes/plain/calls")).json()["items"]
        detail = (await client.get(f"/api/calls/{pdf[0]['id']}")).json()

    assert [c["step_name"] for c in pdf] == [
        "extract key points",
        "write summary",
        "translate to French",
    ]
    assert {c["trace_name"] for c in pdf} == {"Summarize this PDF"}
    assert len({c["trace_id"] for c in pdf}) == 1
    assert len({c["span_id"] for c in pdf}) == 3
    assert (plain[0]["trace_name"], plain[0]["step_name"]) == (None, None)
    assert detail["step_name"] == "extract key points"
    assert detail["trace"]["trace_name"] == "Summarize this PDF"
    assert detail["project"] == PROJECT and detail["trace"]["project"] == PROJECT


async def test_volume_name_with_slash(client):
    plain = await client.get(f"{P}/volumes/team/support/calls")
    encoded = await client.get(f"{P}/volumes/team%2Fsupport/calls")

    assert plain.status_code == encoded.status_code == 200
    assert len(plain.json()["items"]) == len(encoded.json()["items"]) == 1


async def test_the_same_volume_name_in_two_projects_stays_separate(client, session_factory, store):
    await client.post("/api/projects", json={"name": "other"})
    await seed_timed(session_factory, store, volume="alice-chat-42", minutes=3, project="other")

    mine = (await client.get(f"{P}/volumes/alice-chat-42/calls")).json()
    theirs = (await client.get("/api/projects/other/volumes/alice-chat-42/calls")).json()
    export = (await client.get("/api/projects/other/volumes/alice-chat-42/export")).json()

    assert len(mine["items"]) == 2 and {c["project"] for c in mine["items"]} == {PROJECT}
    assert len(theirs["items"]) == 3 and {c["project"] for c in theirs["items"]} == {"other"}
    assert export["project"] == "other" and export["snapshot"]["project"] == "other"
    assert export["snapshot"]["call_count"] == 3


async def test_pagination_with_cursor(client, session_factory, store):
    await seed_timed(session_factory, store)

    first = (await client.get(f"{P}/volumes/timed/calls", params={"limit": 2})).json()
    second = (
        await client.get(
            f"{P}/volumes/timed/calls", params={"limit": 2, "cursor": first["next_cursor"]}
        )
    ).json()

    assert first["has_more"] is True
    assert [c["new_messages"][0]["content"] for c in first["items"] + second["items"]] == [
        "q0",
        "q1",
        "q2",
        "q3",
    ]


async def test_naive_datetimes_are_utc(client, session_factory, store):
    await seed_timed(session_factory, store)

    response = await client.get(
        f"{P}/volumes/timed/export", params={"until": "2026-09-24T10:02:00"}
    )

    assert response.json()["until"] == "2026-09-24T10:02:00Z"
    assert len(response.json()["calls"]) == 3


@pytest.mark.parametrize(
    ("path", "params", "status"),
    [
        (f"{P}/volumes/missing/calls", {}, 404),
        (f"{P}/volumes/alice-chat-42/calls", {"cursor": "garbage"}, 400),
        (f"{P}/volumes/alice-chat-42/calls", {"limit": 0}, 422),
        (f"{P}/volumes/alice-chat-42/calls", {"limit": 501}, 422),
        ("/api/calls/999999", {}, 404),
        (f"{P}/volumes/missing/export", {}, 404),
        (f"{P}/volumes/alice-chat-42/export", {"format": "xml"}, 422),
        (f"{P}/conversations", {"limit": 0}, 422),
    ],
)
async def test_errors(client, path, params, status):
    assert (await client.get(path, params=params)).status_code == status


@pytest.mark.parametrize(
    "path",
    [
        "/api/projects/nope",
        "/api/projects/nope/volumes",
        "/api/projects/nope/conversations",
        "/api/projects/nope/volumes/alice-chat-42/calls",
        "/api/projects/nope/volumes/alice-chat-42/export",
    ],
)
async def test_an_unknown_project_is_a_404_that_names_it(client, path):
    response = await client.get(path)

    assert response.status_code == 404
    assert "Project 'nope' not found" in response.json()["detail"]


async def test_a_volume_of_another_project_is_a_404(client):
    await client.post("/api/projects", json={"name": "other"})

    response = await client.get("/api/projects/other/volumes/alice-chat-42/calls")

    assert response.status_code == 404
    assert "Volume 'alice-chat-42' not found in project 'other'" in response.json()["detail"]


@pytest.mark.parametrize(
    "path",
    ["/api/volumes", "/api/conversations", "/api/volumes/alice-chat-42/calls"],
)
async def test_the_old_addresses_are_gone(client, path):
    assert (await client.get(path)).status_code == 404


# --- one call, exports ---------------------------------------------------------------------------


async def test_get_call_includes_full_trace(client):
    (first, _) = (await client.get(f"{P}/volumes/alice-chat-42/calls")).json()["items"]

    response = await client.get(f"/api/calls/{first['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == first["id"]
    assert detail["trace_error"] is None
    assert detail["trace"]["output_messages"][0]["tool_calls"][0]["name"] == "get_weather"
    assert detail["trace"]["tool_definitions"][0]["name"] == "get_weather"
    assert detail["trace"]["raw_attributes"]["gen_ai.request.model"] == "gpt-4o-mini"


async def test_get_call_with_missing_trace_object(client, store):
    (first, _) = (await client.get(f"{P}/volumes/alice-chat-42/calls")).json()["items"]
    store.objects.clear()

    detail = (await client.get(f"/api/calls/{first['id']}")).json()

    assert detail["trace"] is None
    assert "not found in storage" in detail["trace_error"]
    assert detail["new_messages"]  # index data still available


async def test_json_export(client):
    response = await client.get(f"{P}/volumes/alice-chat-42/export")

    assert response.status_code == 200
    export = response.json()
    assert (export["project"], export["volume"]) == (PROJECT, "alice-chat-42")
    assert export["snapshot"]["project"] == PROJECT
    assert export["snapshot"]["call_count"] == 2
    assert export["snapshot"]["call_ids"] == [c["id"] for c in export["calls"]]
    assert [len(c["input_messages"]) for c in export["calls"]] == [2, 4]


async def test_export_until_excludes_later_calls(client, session_factory, store):
    await seed_timed(session_factory, store)

    export = (
        await client.get(
            f"{P}/volumes/timed/export", params={"until": (T0 + timedelta(minutes=1)).isoformat()}
        )
    ).json()

    assert export["snapshot"]["call_count"] == 2
    assert export["until"] == "2026-09-24T10:01:00Z"


async def test_text_export_reads_as_ordered_transcript(client):
    response = await client.get(f"{P}/volumes/alice-chat-42/export", params={"format": "text"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert text.startswith(f"# Project: {PROJECT}\n# Volume: alice-chat-42\n# 2 calls up to ")
    order = [
        "## Call 1",
        "[user] What's the weather in Paris?",
        '[assistant -> tool call call_1] get_weather({"city": "Paris"})',
        "## Call 2",
        '[tool call_1] {"temp": 22}',
        "[assistant] Sunny, 22°C",
    ]
    positions = [text.index(line) for line in order]
    assert positions == sorted(positions)
    assert text.count("What's the weather in Paris?") == 1  # history is not repeated


async def test_export_with_missing_trace_object_fails_clearly(client, store):
    store.objects.clear()

    response = await client.get(f"{P}/volumes/alice-chat-42/export")

    assert response.status_code == 502
    assert "Export incomplete" in response.json()["detail"]


# --- the web UI calls this API from a browser -----------------------------------------------------

UI = "http://localhost:5173"


async def test_cors_preflight_allows_the_ui_to_create_projects(client):
    response = await client.options(
        "/api/projects",
        headers={
            "origin": UI,
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == UI
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


async def test_cors_headers_are_on_the_responses_the_ui_reads(client):
    created = await client.post("/api/projects", json={"name": "From UI"}, headers={"origin": UI})
    listed = await client.get("/api/projects", headers={"origin": UI})

    assert created.headers["access-control-allow-origin"] == UI
    assert listed.headers["access-control-allow-origin"] == UI


async def test_other_origins_are_not_allowed(client):
    response = await client.options(
        "/api/projects",
        headers={"origin": "http://evil.example", "access-control-request-method": "POST"},
    )

    assert "access-control-allow-origin" not in response.headers
