import gzip

import httpx2
import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from app import repository as repo
from app.main import create_app
from app.storage.base import volume_prefix
from app.storage.memory import InMemoryTraceStore
from tests import spans as s
from tests.spans import PROJECT

PROTOBUF = {"content-type": "application/x-protobuf"}


@pytest.fixture(scope="module")
def captured():
    """Two volumes, a tool call reply, a tool round trip and a failed call — all genuine spans."""
    return s.capture(
        s.chat(volume="alice-chat-42"),
        s.chat(volume="alice-chat-42", reply=s.TOOL_CALL_REPLY, tools=[s.WEATHER_TOOL]),
        s.chat(volume="alice-chat-42", messages=s.TOOL_ROUND_TRIP, tools=[s.WEATHER_TOOL]),
        s.chat(volume="support"),
        s.failing_chat(),
    )


def client_for(session_factory, store):
    app = create_app(session_factory=session_factory, trace_store=store)
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://api")


async def calls_in(session_factory, volume, project=PROJECT):
    async with session_factory() as session:
        return (await repo.list_calls(session, project, volume)).items


async def create_project(session_factory, name):
    async with session_factory() as session:
        await repo.create_project(session, name)
        await session.commit()


async def test_protobuf_export_is_stored_in_s3_and_postgres(session_factory, s3_store, captured):
    async with client_for(session_factory, s3_store) as client:
        response = await client.post(
            "/v1/traces", content=s.to_protobuf(captured), headers=PROTOBUF
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-protobuf"
    assert (
        ExportTraceServiceResponse.FromString(response.content).partial_success.rejected_spans == 0
    )

    alice = await calls_in(session_factory, "alice-chat-42")
    assert len(alice) == 3
    assert alice[1].tool_calls_made == ["get_weather"]
    assert [m["role"] for m in alice[2].preview] == ["tool", "assistant"]
    assert len(await calls_in(session_factory, "support")) == 1
    (failed,) = await calls_in(session_factory, "default")
    assert (failed.status, failed.error_type) == ("error", "RateLimitError")

    keys = await s3_store.list_prefix(volume_prefix(PROJECT, "alice-chat-42"))
    assert sorted(keys) == sorted(c.trace_key for c in alice)
    trace = await s3_store.get(alice[1].trace_key)
    assert trace["output_messages"][0]["tool_calls"][0]["arguments"] == {"city": "Paris"}
    assert trace["raw_attributes"]["aicontrol.volume"] == "alice-chat-42"


async def test_json_export_is_stored(session_factory, captured):
    store = InMemoryTraceStore()
    async with client_for(session_factory, store) as client:
        response = await client.post(
            "/v1/traces",
            content=s.to_otlp_json(captured),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json() == {}
    assert len(await calls_in(session_factory, "alice-chat-42")) == 3
    assert len(store.objects) == 5


async def test_gzip_body_is_accepted(session_factory, captured):
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        response = await client.post(
            "/v1/traces",
            content=gzip.compress(s.to_protobuf(captured)),
            headers={**PROTOBUF, "content-encoding": "gzip"},
        )

    assert response.status_code == 200
    assert len(await calls_in(session_factory, "alice-chat-42")) == 3


async def test_malformed_span_is_rejected_and_the_rest_stored(session_factory, captured):
    body = s.with_broken_span_id(s.to_request(captured), index=0)
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        response = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert response.status_code == 200
    partial = ExportTraceServiceResponse.FromString(response.content).partial_success
    assert partial.rejected_spans == 1
    assert "Invalid trace/span id" in partial.error_message
    assert len(await calls_in(session_factory, "alice-chat-42")) == 2


async def test_same_batch_twice_is_stored_once(session_factory, s3_store, captured):
    async with client_for(session_factory, s3_store) as client:
        for _ in range(2):
            response = await client.post(
                "/v1/traces", content=s.to_protobuf(captured), headers=PROTOBUF
            )
            assert response.status_code == 200

    assert len(await calls_in(session_factory, "alice-chat-42")) == 3
    assert len(await s3_store.list_prefix(volume_prefix(PROJECT, "alice-chat-42"))) == 3


async def test_storage_failure_asks_exporter_to_retry(session_factory, captured):
    class DownStore(InMemoryTraceStore):
        async def put(self, key, document):
            raise ConnectionError("S3 is down")

    async with client_for(session_factory, DownStore()) as client:
        response = await client.post(
            "/v1/traces", content=s.to_protobuf(captured), headers=PROTOBUF
        )

    assert response.status_code == 503
    assert await calls_in(session_factory, "alice-chat-42") == []


async def test_undecodable_body_is_a_client_error(session_factory):
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        response = await client.post("/v1/traces", content=b"\xff\xff", headers=PROTOBUF)

    assert response.status_code == 400


async def test_non_llm_spans_are_ignored(session_factory):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("web").start_as_current_span(
        "GET /", attributes={"http.method": "GET"}
    ):
        pass
    store = InMemoryTraceStore()

    async with client_for(session_factory, store) as client:
        response = await client.post(
            "/v1/traces",
            content=s.to_protobuf(list(exporter.get_finished_spans())),
            headers=PROTOBUF,
        )

    assert response.status_code == 200
    async with session_factory() as session:
        assert await repo.list_volumes(session, PROJECT) == []
    assert store.objects == {}


# --- projects: calls are only accepted for a project that exists -------------------------------

ERROR_HEADER = "x-aicontrol-error"


async def test_calls_for_an_unknown_project_are_rejected_with_a_clear_error(session_factory):
    body = s.to_protobuf(s.capture(s.chat(volume="chat"), project="ghost-project"))
    store = InMemoryTraceStore()
    async with client_for(session_factory, store) as client:
        response = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert response.status_code == 404
    assert response.headers[ERROR_HEADER] == "project-not-found"
    assert "ghost-project" in response.text and "slug" in response.text
    assert "Create the project" in response.text
    assert store.objects == {}
    assert await calls_in(session_factory, "chat", project="ghost-project") == []
    async with session_factory() as session:
        assert await repo.get_project(session, "ghost-project") is None  # never auto-created


async def test_the_same_calls_flow_once_the_project_has_been_created(session_factory):
    body = s.to_protobuf(s.capture(s.chat(volume="chat"), project="late-project"))
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        first = await client.post("/v1/traces", content=body, headers=PROTOBUF)
        await create_project(session_factory, "Late Project")  # its slug is late-project
        second = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert (first.status_code, second.status_code) == (404, 200)
    assert len(await calls_in(session_factory, "chat", project="late-project")) == 1


async def test_json_exports_get_the_same_rejection(session_factory):
    body = s.to_otlp_json(s.capture(s.chat(), project="ghost"))
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        response = await client.post(
            "/v1/traces", content=body, headers={"content-type": "application/json"}
        )

    assert response.status_code == 404
    assert response.headers[ERROR_HEADER] == "project-not-found"


async def test_spans_without_a_project_are_a_client_error(session_factory, captured):
    body = s.without_project(s.to_request(captured))
    store = InMemoryTraceStore()
    async with client_for(session_factory, store) as client:
        response = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert response.status_code == 400
    assert response.headers[ERROR_HEADER] == "project-missing"
    assert "aicontrol.init(project=" in response.text
    assert store.objects == {}


async def test_a_request_mixing_known_and_unknown_projects_stores_the_known_ones(session_factory):
    known = s.capture(s.chat(volume="chat"), s.chat(volume="chat"), project=PROJECT)
    unknown = s.capture(s.chat(volume="chat"), project="ghost")
    body = s.to_protobuf(known + unknown)
    store = InMemoryTraceStore()
    async with client_for(session_factory, store) as client:
        response = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert response.status_code == 200
    partial = ExportTraceServiceResponse.FromString(response.content).partial_success
    assert partial.rejected_spans == 1
    assert "ghost" in partial.error_message and "not found" in partial.error_message
    assert len(await calls_in(session_factory, "chat")) == 2
    assert len(store.objects) == 2


async def test_one_request_can_hold_several_existing_projects(session_factory):
    await create_project(session_factory, "other")
    body = s.to_protobuf(
        s.capture(s.chat(volume="chat"), project=PROJECT)
        + s.capture(s.chat(volume="chat"), project="other")
    )
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        response = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert response.status_code == 200
    assert len(await calls_in(session_factory, "chat")) == 1
    assert len(await calls_in(session_factory, "chat", project="other")) == 1


async def test_calls_are_stored_under_the_slug_of_a_project_not_its_name(session_factory):
    await create_project(session_factory, "My Project")  # slug: my-project
    store = InMemoryTraceStore()
    async with client_for(session_factory, store) as client:
        response = await client.post(
            "/v1/traces",
            content=s.to_protobuf(s.capture(s.chat(volume="alice-chat-42"), project="my-project")),
            headers=PROTOBUF,
        )

    assert response.status_code == 200
    (call,) = await calls_in(session_factory, "alice-chat-42", project="my-project")
    assert (call.volume.project.slug, call.volume.project.name) == ("my-project", "My Project")
    assert call.trace_key.startswith("projects/my-project/volumes/alice-chat-42/")
    assert call.trace_key in store.objects


async def test_the_project_name_is_not_accepted_in_place_of_the_slug(session_factory):
    await create_project(session_factory, "My Project")  # slug: my-project
    spans = s.capture(s.chat(volume="chat"), project="my-project")
    body = s.to_protobuf(spans).replace(b"my-project", b"My Project")  # as if the name was sent
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        response = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert response.status_code == 404
    assert response.headers[ERROR_HEADER] == "project-not-found"
    assert "My Project" in response.text and "slug" in response.text


async def test_non_llm_spans_of_an_unknown_project_are_still_just_ignored(session_factory):
    """The parent span `aicontrol.trace()` opens is not an LLM call, whatever its project."""
    body = s.to_protobuf(s.capture(s.traced("Plan", ("step", s.chat())), project=PROJECT))
    async with client_for(session_factory, InMemoryTraceStore()) as client:
        response = await client.post("/v1/traces", content=body, headers=PROTOBUF)

    assert response.status_code == 200
    assert len(await calls_in(session_factory, "default")) == 1
