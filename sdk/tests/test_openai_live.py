"""Live capture test against the real OpenAI API — no mocks.

Opt-in: `uv run pytest -m e2e`. Needs OPENAI_API_KEY (environment or the repository's root
`.env`). Model defaults to gpt-4o-mini; override with AICONTROL_E2E_MODEL.
"""

import json
import os
from pathlib import Path

import pytest

import aicontrol

pytestmark = pytest.mark.e2e

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


def _setting(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if ROOT_ENV.exists():
        for line in ROOT_ENV.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name and value.strip():
                return value.strip().strip("'\"")
    return None


@pytest.fixture
def openai_client():
    api_key = _setting("OPENAI_API_KEY")
    if not api_key:
        pytest.skip(f"OPENAI_API_KEY not set (environment or {ROOT_ENV})")
    import openai

    return openai.OpenAI(api_key=api_key)


def test_real_chat_with_tool_is_captured(exporter, openai_client):
    model = _setting("AICONTROL_E2E_MODEL") or "gpt-4o-mini"
    weather_tool = {
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

    with aicontrol.volume("e2e-live"):
        reply = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "What's the weather in Paris? Use the tool."}],
            tools=[weather_tool],
            tool_choice={"type": "function", "function": {"name": "get_weather"}},
            max_tokens=50,
        )

    assert reply.choices[0].message.tool_calls
    (span,) = exporter.get_finished_spans()
    a = span.attributes
    assert a["aicontrol.volume"] == "e2e-live"
    assert a["gen_ai.request.model"] == model
    assert a["gen_ai.response.model"].startswith(model)
    assert a["gen_ai.usage.input_tokens"] > 0
    assert a["gen_ai.usage.output_tokens"] > 0
    (output,) = json.loads(a["gen_ai.output.messages"])
    tool_call = next(p for p in output["parts"] if p["type"] == "tool_call")
    assert tool_call["name"] == "get_weather"
    assert "paris" in json.dumps(tool_call["arguments"]).lower()
