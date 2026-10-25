import json
import time

import openai
import pytest
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

import aicontrol
from tests.fixtures import openai_responses as r

MESSAGES = [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "What's the weather in Paris?"},
]


def only_span(exporter):
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["openai.chat"]
    return spans[0]


def test_sync_chat_captures_messages_settings_usage_and_volume(exporter):
    client = r.client(r.json_handler(r.TEXT_REPLY))

    with aicontrol.volume("alice-chat-42"):
        reply = client.chat.completions.create(
            model="gpt-4o-mini", messages=MESSAGES, temperature=0.2, max_tokens=100, top_p=0.9
        )

    assert reply.choices[0].message.content == "Sunny, 22°C"
    a = only_span(exporter).attributes
    assert a["aicontrol.volume"] == "alice-chat-42"
    assert a["gen_ai.provider.name"] == "openai"
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.request.model"] == "gpt-4o-mini"
    assert a["gen_ai.request.temperature"] == 0.2
    assert a["gen_ai.request.max_tokens"] == 100
    assert a["gen_ai.request.top_p"] == 0.9
    assert a["gen_ai.response.model"] == "gpt-4o-mini-2024-07-18"
    assert a["gen_ai.response.id"] == "chatcmpl-123"
    assert tuple(a["gen_ai.response.finish_reasons"]) == ("stop",)
    assert a["gen_ai.usage.input_tokens"] == 45
    assert a["gen_ai.usage.output_tokens"] == 8
    assert a["gen_ai.usage.total_tokens"] == 53
    assert a["gen_ai.usage.cache_read.input_tokens"] == 10
    assert a["gen_ai.usage.reasoning_tokens"] == 3
    assert a["gen_ai.is_streaming"] is False

    inputs = json.loads(a["gen_ai.input.messages"])
    assert [m["role"] for m in inputs] == ["system", "user"]
    assert inputs[1]["parts"] == [{"type": "text", "content": "What's the weather in Paris?"}]
    outputs = json.loads(a["gen_ai.output.messages"])
    assert outputs[0]["role"] == "assistant"
    assert outputs[0]["parts"] == [{"type": "text", "content": "Sunny, 22°C"}]


def test_streaming_chat_produces_one_span_after_stream_is_consumed(exporter):
    client = r.client(r.sse_handler(r.stream_body(["Sunny", ", 22", "°C"])))

    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=MESSAGES,
        stream=True,
        stream_options={"include_usage": True},
    )
    assert exporter.get_finished_spans() == ()
    text = "".join(c.choices[0].delta.content or "" for c in stream if c.choices)

    assert text == "Sunny, 22°C"
    a = only_span(exporter).attributes
    assert a["gen_ai.is_streaming"] is True
    assert json.loads(a["gen_ai.output.messages"])[0]["parts"] == [
        {"type": "text", "content": "Sunny, 22°C"}
    ]
    assert a["gen_ai.usage.input_tokens"] == 45
    assert a["gen_ai.usage.output_tokens"] == 8


async def test_async_chat_carries_volume(exporter):
    client = r.async_client(r.json_handler(r.TEXT_REPLY))

    async with aicontrol.volume("async-vol"):
        await client.chat.completions.create(model="gpt-4o-mini", messages=MESSAGES)

    assert only_span(exporter).attributes["aicontrol.volume"] == "async-vol"


def test_tool_call_in_reply_and_tool_definitions_are_captured(exporter):
    client = r.client(r.json_handler(r.TOOL_CALL_REPLY))

    client.chat.completions.create(model="gpt-4o-mini", messages=MESSAGES, tools=[r.WEATHER_TOOL])

    a = only_span(exporter).attributes
    assert tuple(a["gen_ai.response.finish_reasons"]) == ("tool_call",)
    tools = json.loads(a["gen_ai.tool.definitions"])
    assert [t["name"] for t in tools] == ["get_weather"]
    (reply,) = json.loads(a["gen_ai.output.messages"])
    assert reply["parts"] == [
        {"type": "tool_call", "name": "get_weather", "id": "call_1", "arguments": {"city": "Paris"}}
    ]


def test_tool_round_trip_is_captured_in_input(exporter):
    client = r.client(r.json_handler(r.TEXT_REPLY))
    history = MESSAGES + [
        r.TOOL_CALL_REPLY["choices"][0]["message"],
        {"role": "tool", "tool_call_id": "call_1", "content": '{"temp": 22, "sky": "sunny"}'},
    ]

    client.chat.completions.create(model="gpt-4o-mini", messages=history, tools=[r.WEATHER_TOOL])

    inputs = json.loads(only_span(exporter).attributes["gen_ai.input.messages"])
    assert [m["role"] for m in inputs] == ["system", "user", "assistant", "tool"]
    assert inputs[2]["parts"][0]["type"] == "tool_call"
    assert inputs[2]["parts"][0]["name"] == "get_weather"
    assert inputs[3]["parts"][0]["type"] == "tool_call_response"
    assert inputs[3]["parts"][0]["id"] == "call_1"


def test_openai_error_is_recorded_and_reaches_the_app_unchanged(exporter):
    error_body = {"error": {"message": "Rate limit", "type": "rate_limit_error", "code": None}}
    client = r.client(r.json_handler(error_body, status=429))

    with pytest.raises(openai.RateLimitError):
        client.chat.completions.create(model="gpt-4o-mini", messages=MESSAGES)

    span = only_span(exporter)
    assert span.status.is_ok is False
    assert span.attributes["error.type"] == "RateLimitError"


def test_openai_compatible_base_url_is_captured(exporter):
    client = r.client(r.json_handler(r.TEXT_REPLY), base_url="http://localhost:11434/v1")

    client.chat.completions.create(model="llama3.2", messages=MESSAGES)

    assert only_span(exporter).attributes["gen_ai.openai.api_base"] == "http://localhost:11434/v1/"


def test_unreachable_aicontrol_api_does_not_affect_the_app():
    unreachable = OTLPSpanExporter(endpoint="http://127.0.0.1:9/v1/traces", timeout=1)
    aicontrol.init(project="test-app", span_exporter=unreachable)  # batched, as in production
    client = r.client(r.json_handler(r.TEXT_REPLY))
    try:
        start = time.monotonic()
        reply = client.chat.completions.create(model="gpt-4o-mini", messages=MESSAGES)
        elapsed = time.monotonic() - start
    finally:
        aicontrol.shutdown()

    assert reply.choices[0].message.content == "Sunny, 22°C"
    assert elapsed < 0.5


def test_no_span_after_shutdown(exporter):
    aicontrol.shutdown()
    client = r.client(r.json_handler(r.TEXT_REPLY))

    client.chat.completions.create(model="gpt-4o-mini", messages=MESSAGES)

    assert exporter.get_finished_spans() == ()


def test_repeated_init_shutdown_cycles_capture_each_call_exactly_once():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    body = r.stream_body(["Sunny", ", 22", "°C"])
    for _ in range(5):
        exporter = InMemorySpanExporter()
        aicontrol.init(project="cycle", span_exporter=exporter, batch=False)
        try:
            stream = r.client(r.sse_handler(body)).chat.completions.create(
                model="gpt-4o-mini", messages=MESSAGES, stream=True
            )
            list(stream)
        finally:
            aicontrol.shutdown()

        (span,) = exporter.get_finished_spans()
        assert span.resource.attributes["service.name"] == "cycle"
        assert json.loads(span.attributes["gen_ai.output.messages"])[0]["parts"] == [
            {"type": "text", "content": "Sunny, 22°C"}
        ]


def test_missing_openai_package_logs_warning_and_skips(monkeypatch, caplog):
    from aicontrol import _instrument

    monkeypatch.setattr(_instrument, "_instrumented", False)
    monkeypatch.setattr(_instrument.importlib.util, "find_spec", lambda name: None)

    _instrument.instrument(lambda: None)

    assert "`openai` is not installed" in caplog.text
    assert _instrument._instrumented is False
