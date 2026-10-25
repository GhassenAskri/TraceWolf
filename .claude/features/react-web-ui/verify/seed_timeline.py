"""Timeline test data in the THROWAWAY database: a 120-call conversation and a hostile one."""
import asyncio
from datetime import UTC, datetime, timedelta

from app import repository as repo
from app.db import create_engine, create_session_factory
from app.repository import NewCall

URL = "postgresql+psycopg://aicontrol:aicontrol@localhost:5543/aicontrol"
T0 = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
HOSTILE = "<img src=x onerror=alert(1)>"


def call(volume: str, i: int, at: datetime, user: str, assistant: str) -> NewCall:
    return NewCall(
        volume=volume, trace_id=f"{i:032x}", span_id=f"{i:016x}", started_at=at,
        ended_at=at + timedelta(milliseconds=300 + i % 50), trace_key=f"volumes/seed-timeline/{i}.json",
        request_model="gpt-4o-mini", response_model="gpt-4o-mini-2024-07-18",
        input_tokens=20 + i % 100, output_tokens=5 + i % 7, latency_ms=300 + i % 50, status="ok",
        finish_reasons=["stop"],
        preview=[{"role": "user", "content": user},
                 {"role": "assistant", "content": assistant, "finish_reason": "stop"}],
    )


async def main() -> None:
    long_calls = [call("timeline-long", 10_000 + i, T0 + timedelta(minutes=i), f"question {i}", f"answer {i}") for i in range(120)]
    hostile = [call(HOSTILE, 20_000, T0, '<script>alert("x")</script>', '<b>bold</b> & "quotes" <i>tags</i>')]
    edge = [
        # everything unknown: no model, tokens, latency, finish reasons or messages; streamed
        NewCall(volume="edge-cases", trace_id=f"{30_000:032x}", span_id=f"{30_000:016x}", started_at=T0,
                trace_key="volumes/seed-edge/1.json", is_streaming=True, preview=[]),
        # an error with zero latency, 0 cached/reasoning tokens (hidden), two finish reasons, 3 tools,
        # multi-line text, an assistant message with neither text nor tool calls
        NewCall(volume="edge-cases", trace_id=f"{30_001:032x}", span_id=f"{30_001:016x}",
                started_at=T0 + timedelta(minutes=1), ended_at=T0 + timedelta(minutes=1),
                trace_key="volumes/seed-edge/2.json", request_model="gpt-4o-mini", latency_ms=0,
                input_tokens=7, output_tokens=None, cached_input_tokens=0, reasoning_tokens=0,
                status="error", error_type="TimeoutError", finish_reasons=["length", "stop"], tools_offered=3,
                preview=[{"role": "user", "content": "line one\nline two\n\n   indented  \"quoted\" & <tag>"},
                         {"role": "assistant", "content": None}]),
        # one tool offered ("1 tool"), a tool call with nested arguments
        NewCall(volume="edge-cases", trace_id=f"{30_002:032x}", span_id=f"{30_002:016x}",
                started_at=T0 + timedelta(minutes=2), trace_key="volumes/seed-edge/3.json",
                request_model="gpt-4o-mini", response_model="gpt-4o-2024-08-06", latency_ms=12345,
                input_tokens=1200, output_tokens=300, cached_input_tokens=1000, reasoning_tokens=64,
                is_streaming=False, finish_reasons=["tool_call"], tools_offered=1,
                preview=[{"role": "assistant", "content": None, "tool_calls": [
                    {"id": "call_9", "name": "search", "arguments": {"q": "caf\u00e9 \u2615", "filters": {"tags": ["a", "b"], "n": 3, "ok": True, "none": None}}}]}]),
    ]
    engine = create_engine(URL)
    async with create_session_factory(engine)() as session:
        await repo.insert_calls(session, long_calls + hostile + edge)
        await session.commit()
    await engine.dispose()
    print("seeded timeline-long (120 calls) and the hostile conversation")


asyncio.run(main())
