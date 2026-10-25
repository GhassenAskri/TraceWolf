"""End-to-end, no mocks: real LLM API → aicontrol SDK (real batched OTLP exporter) → real
AIControl API → real Postgres + MinIO → REST API / export.

Opt-in: `uv run pytest -m e2e`. Needs OPENAI_API_KEY (environment or root `.env`).
Optional: AICONTROL_E2E_MODEL (default gpt-4o-mini), AICONTROL_E2E_BASE_URL (OpenAI-compatible
server such as a local Ollama).
"""

import asyncio
import json
import uuid

import aicontrol
import httpx2
import openai
import pytest

from app.storage.base import volume_prefix
from app.storage.s3 import S3TraceStore

pytestmark = pytest.mark.e2e

PROJECT = "e2e-project"
P = f"/api/projects/{PROJECT}"
WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


def create_project(api_server, name):
    """Projects are created explicitly (the web UI does this); 409 means it already exists."""
    base_url, _ = api_server
    response = httpx2.post(f"{base_url}/api/projects", json={"name": name}, timeout=30)
    assert response.status_code in (201, 409), response.text


@pytest.fixture
def sdk(api_server):
    base_url, _ = api_server
    create_project(api_server, PROJECT)
    aicontrol.init(endpoint=base_url, project=PROJECT)  # production setup: batched exporter
    yield
    aicontrol.shutdown()


@pytest.fixture
def client(llm):
    return openai.OpenAI(api_key=llm["api_key"], base_url=llm["base_url"])


@pytest.fixture
def run_id():
    return uuid.uuid4().hex[:8]


def api_get(api_server, path, **params):
    base_url, _ = api_server
    response = httpx2.get(f"{base_url}{path}", params=params, timeout=30)
    response.raise_for_status()
    return response


def s3_keys(api_server, volume):
    _, settings = api_server

    async def list_keys():
        async with S3TraceStore(
            settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        ) as store:
            return await store.list_prefix(volume_prefix(PROJECT, volume))

    return asyncio.run(list_keys())


def test_tool_conversation_streaming_and_volumes(sdk, client, llm, api_server, run_id):
    chat_volume, other_volume = f"e2e-chat-{run_id}", f"e2e-other-{run_id}"
    model = llm["model"]
    history = [
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "What's the weather in Paris? Use the tool."},
    ]

    with aicontrol.volume(chat_volume):
        # 1) the model asks for the tool
        first = client.chat.completions.create(
            model=model,
            messages=history,
            tools=[WEATHER_TOOL],
            max_tokens=100,
            tool_choice={"type": "function", "function": {"name": "get_weather"}},
        )
        tool_call = first.choices[0].message.tool_calls[0]
        history.append(first.choices[0].message.model_dump(exclude_none=True))
        # 2) the app runs the tool and sends the result back
        history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps({"temp_c": 22, "sky": "sunny"}),
            }
        )
        second = client.chat.completions.create(
            model=model, messages=history, tools=[WEATHER_TOOL], max_tokens=100
        )
        history.append({"role": "assistant", "content": second.choices[0].message.content})
        # 3) a streamed follow-up
        history.append({"role": "user", "content": "Answer in one word: is that warm?"})
        stream = client.chat.completions.create(
            model=model,
            messages=history,
            max_tokens=20,
            stream=True,
            stream_options={"include_usage": True},
        )
        streamed_text = "".join(c.choices[0].delta.content or "" for c in stream if c.choices)

    with aicontrol.volume(other_volume):
        client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "Say hi."}], max_tokens=10
        )

    assert aicontrol.flush()

    # Volumes are listed with the right counts.
    volumes = {v["name"]: v for v in api_get(api_server, f"/api/projects/{PROJECT}/volumes").json()}
    assert volumes[chat_volume]["call_count"] == 3
    assert volumes[other_volume]["call_count"] == 1

    # Calls: order, tool calls, tool results, streaming, monitoring columns.
    calls = api_get(api_server, f"{P}/volumes/{chat_volume}/calls").json()["items"]
    assert len(calls) == 3
    tool_turn, tool_result_turn, streamed_turn = calls
    assert tool_turn["tool_calls_made"] == ["get_weather"]
    assert tool_turn["finish_reasons"] == ["tool_call"]
    assert tool_turn["tools_offered"] == 1
    assert [m["role"] for m in tool_result_turn["new_messages"]] == ["tool", "assistant"]
    assert tool_result_turn["new_messages"][0]["tool_call_id"] == tool_call.id
    assert streamed_turn["is_streaming"] is True
    assert streamed_turn["new_messages"][-1]["content"] == streamed_text
    for call in calls:
        assert call["request_model"] == model
        assert call["response_model"]
        assert call["status"] == "ok"
        assert call["project"] == PROJECT
        assert call["tokens"]["input"] > 0 and call["tokens"]["output"] > 0
        assert call["latency_ms"] > 0

    # Full trace from S3.
    detail = api_get(api_server, f"/api/calls/{tool_turn['id']}").json()
    assert detail["trace_error"] is None
    (reply,) = detail["trace"]["output_messages"]
    assert reply["tool_calls"][0]["name"] == "get_weather"
    assert "paris" in json.dumps(reply["tool_calls"][0]["arguments"]).lower()
    assert detail["trace"]["tool_definitions"][0]["name"] == "get_weather"

    # Objects are stored under the volume's prefix in MinIO.
    assert len(s3_keys(api_server, chat_volume)) == 3
    assert len(s3_keys(api_server, other_volume)) == 1

    # Export (JSON + text) is ordered and complete.
    export = api_get(api_server, f"{P}/volumes/{chat_volume}/export").json()
    assert export["snapshot"]["call_ids"] == [c["id"] for c in calls]
    transcript = api_get(api_server, f"{P}/volumes/{chat_volume}/export", format="text").text
    assert transcript.index("[assistant -> tool call") < transcript.index("[tool ")
    assert transcript.count("What's the weather in Paris?") == 1


def test_calls_for_a_missing_project_are_refused_then_flow_once_it_is_created(
    client, llm, api_server, run_id, caplog
):
    """The SDK's view of the whole project flow: an error is logged once and the application is
    unaffected, then calls arrive as soon as the project has been created in the UI."""
    base_url, _ = api_server
    project = f"late-project-{run_id}"
    ask = {
        "model": llm["model"],
        "messages": [{"role": "user", "content": "Say hi."}],
        "max_tokens": 10,
    }
    caplog.set_level("ERROR", logger="aicontrol")

    aicontrol.init(endpoint=base_url, project=project)
    try:
        client.chat.completions.create(**ask)  # the application is not affected
        assert aicontrol.flush()
        client.chat.completions.create(**ask)
        assert aicontrol.flush()

        assert httpx2.get(f"{base_url}/api/projects/{project}", timeout=30).status_code == 404
        refusals = [
            r for r in caplog.records if r.name == "aicontrol" and "does not exist" in r.message
        ]
        assert len(refusals) == 1 and project in refusals[0].getMessage()  # logged once

        create_project(api_server, project)  # in the UI: New project
        with aicontrol.volume("after"):
            client.chat.completions.create(**ask)
        assert aicontrol.flush()
    finally:
        aicontrol.shutdown()

    (call,) = httpx2.get(
        f"{base_url}/api/projects/{project}/volumes/after/calls", timeout=30
    ).json()["items"]
    assert call["project"] == project
