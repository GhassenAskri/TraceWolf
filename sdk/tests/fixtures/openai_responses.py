"""Canned OpenAI Chat Completions responses and clients wired to an in-process mock transport.

`openai` 3.x uses `httpx2`, so `respx` (which patches `httpx`) does not intercept it. Clients get
an `httpx2.MockTransport` directly: requests can never leave the machine.
"""

import json
from collections.abc import Callable

import httpx2
import openai

BASE_URL = "http://openai.test/v1"

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

USAGE = {
    "prompt_tokens": 45,
    "completion_tokens": 8,
    "total_tokens": 53,
    "prompt_tokens_details": {"cached_tokens": 10},
    "completion_tokens_details": {"reasoning_tokens": 3},
}


def completion(message: dict, finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1_790_000_000,
        "model": "gpt-4o-mini-2024-07-18",
        "system_fingerprint": "fp_test",
        "service_tier": "default",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": USAGE,
    }


TEXT_REPLY = completion({"role": "assistant", "content": "Sunny, 22°C"})

TOOL_CALL_REPLY = completion(
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            }
        ],
    },
    finish_reason="tool_calls",
)


def stream_body(chunks: list[str]) -> bytes:
    """Server-sent events for a streamed text reply, ending with a usage-only chunk."""
    base = {
        "id": "chatcmpl-123",
        "object": "chat.completion.chunk",
        "created": 1_790_000_000,
        "model": "gpt-4o-mini-2024-07-18",
    }
    events = [{**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]}]
    events += [{**base, "choices": [{"index": 0, "delta": {"content": c}}]} for c in chunks]
    events.append({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    events.append({**base, "choices": [], "usage": USAGE})
    lines = [f"data: {json.dumps(e)}\n\n" for e in events] + ["data: [DONE]\n\n"]
    return "".join(lines).encode()


Handler = Callable[[httpx2.Request], httpx2.Response]


def json_handler(body: dict, status: int = 200) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/chat/completions"), request.url
        return httpx2.Response(status, json=body)

    return handler


def sse_handler(body: bytes) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"})

    return handler


def client(handler: Handler, base_url: str = BASE_URL) -> openai.OpenAI:
    return openai.OpenAI(
        api_key="sk-test",
        base_url=base_url,
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def async_client(handler: Handler, base_url: str = BASE_URL) -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        api_key="sk-test",
        base_url=base_url,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
