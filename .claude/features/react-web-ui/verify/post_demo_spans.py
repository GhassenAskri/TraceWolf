"""Genuine SDK-instrumented calls (mocked OpenAI) posted to the real ingest endpoint: a tool-call
conversation and a conversation with a failing call."""
import aicontrol
import httpx2

from tests import spans as s


def failing_in(volume: str):
    def call():
        with aicontrol.volume(volume):
            s.failing_chat()()
    return call


calls = [
    s.chat(volume="tools-demo", reply=s.TOOL_CALL_REPLY, tools=[s.WEATHER_TOOL]),
    s.chat(volume="tools-demo", messages=s.TOOL_ROUND_TRIP, tools=[s.WEATHER_TOOL]),
    s.chat(volume="error-demo"),
    failing_in("error-demo"),
    # hostile text inside a stored trace (shown by "Show full input")
    s.chat(
        volume="hostile-trace",
        messages=[
            {"role": "system", "content": "<img src=x onerror=alert(2)>"},
            {"role": "user", "content": '<script>alert("t")</script> & "quotes"'},
        ],
    ),
]
body = s.to_protobuf(s.capture(*calls))
r = httpx2.post("http://127.0.0.1:8011/v1/traces", content=body,
                headers={"content-type": "application/x-protobuf"}, timeout=20)
print("demo spans POST /v1/traces ->", r.status_code)
