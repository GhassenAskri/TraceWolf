"""Genuine OpenAI spans for ingest tests: the aicontrol SDK + OpenLLMetry instrumentor capture
calls made against an in-process mock of the OpenAI API, then spans are encoded exactly as the
OTLP/HTTP exporter does."""

from __future__ import annotations

import base64
import copy
import json
from collections.abc import Callable

import aicontrol
import httpx2
import openai
from google.protobuf import json_format
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# The project every integration test starts with (see tests/integration/conftest.py).
PROJECT = "test-project"

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather for a city",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
    },
}
USAGE = {
    "prompt_tokens": 45,
    "completion_tokens": 8,
    "total_tokens": 53,
    "prompt_tokens_details": {"cached_tokens": 10},
    "completion_tokens_details": {"reasoning_tokens": 3},
}
QUESTION = [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "What's the weather in Paris?"},
]
TOOL_CALL_MESSAGE = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
        }
    ],
}
TOOL_ROUND_TRIP = [
    *QUESTION,
    TOOL_CALL_MESSAGE,
    {"role": "tool", "tool_call_id": "call_1", "content": '{"temp": 22}'},
]


def completion(message: dict, finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1_790_000_000,
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": USAGE,
    }


TEXT_REPLY = completion({"role": "assistant", "content": "Sunny, 22°C"})
TOOL_CALL_REPLY = completion(TOOL_CALL_MESSAGE, "tool_calls")


def _client(body: dict, status: int = 200) -> openai.OpenAI:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json=body)

    return openai.OpenAI(
        api_key="sk-test",
        base_url="http://openai.test/v1",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def capture(*calls: Callable[[], None], project: str = PROJECT) -> list[ReadableSpan]:
    """Run the given call functions with the SDK active and return the finished spans."""
    exporter = InMemorySpanExporter()
    aicontrol.init(project=project, span_exporter=exporter, batch=False)
    try:
        for call in calls:
            call()
    finally:
        aicontrol.shutdown()
    return list(exporter.get_finished_spans())


def chat(reply: dict = TEXT_REPLY, messages=QUESTION, volume: str | None = None, **kwargs):
    def call():
        client = _client(reply)
        if volume is None:
            client.chat.completions.create(model="gpt-4o-mini", messages=messages, **kwargs)
        else:
            with aicontrol.volume(volume):
                client.chat.completions.create(model="gpt-4o-mini", messages=messages, **kwargs)

    return call


def traced(name: str, *steps: tuple[str, Callable[[], None]]) -> Callable[[], None]:
    """Run the given `(step name, call)` pairs inside `aicontrol.trace(name)`, each in its step."""

    def call():
        with aicontrol.trace(name):
            for step_name, step_call in steps:
                with aicontrol.step(step_name):
                    step_call()

    return call


def failing_chat(status: int = 429):
    def call():
        body = {"error": {"message": "Rate limit", "type": "rate_limit_error"}}
        try:
            _client(body, status).chat.completions.create(model="gpt-4o-mini", messages=QUESTION)
        except openai.APIStatusError:
            pass

    return call


def to_request(spans: list[ReadableSpan]) -> ExportTraceServiceRequest:
    return encode_spans(spans)


def to_protobuf(spans: list[ReadableSpan]) -> bytes:
    return to_request(spans).SerializeToString()


def to_otlp_json(spans: list[ReadableSpan]) -> bytes:
    """OTLP/JSON: protobuf JSON mapping, except trace/span ids are hex strings."""
    payload = json_format.MessageToDict(to_request(spans))
    for rs in payload.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                for key in ("traceId", "spanId", "parentSpanId"):
                    if span.get(key):
                        span[key] = base64.b64decode(span[key]).hex()
    return json.dumps(payload).encode()


def with_broken_span_id(request: ExportTraceServiceRequest, index: int = 0) -> bytes:
    broken = copy.deepcopy(request)
    broken.resource_spans[0].scope_spans[0].spans[index].span_id = b"\x01"
    return broken.SerializeToString()


def without_project(request: ExportTraceServiceRequest) -> bytes:
    """The request as an SDK without a project (an old version) would have sent it."""
    stripped = copy.deepcopy(request)
    for resource_spans in stripped.resource_spans:
        kept = [a for a in resource_spans.resource.attributes if a.key != "aicontrol.project"]
        del resource_spans.resource.attributes[:]
        resource_spans.resource.attributes.extend(kept)
    return stripped.SerializeToString()
