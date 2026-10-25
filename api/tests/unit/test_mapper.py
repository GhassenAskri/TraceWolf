import logging
from dataclasses import replace

import pytest

from app.ingest import mapper, otlp
from tests import spans as s


def decoded(*calls, project=s.PROJECT):
    return otlp.decode_request(s.to_protobuf(s.capture(*calls, project=project)), otlp.PROTOBUF)


def test_text_reply_maps_monitoring_columns_and_trace():
    (span,) = decoded(s.chat(volume="alice-chat-42", temperature=0.2, max_tokens=100, top_p=0.9))

    call = mapper.map_span(span)

    row = call.row
    assert row.volume == "alice-chat-42"
    assert (row.trace_id, row.span_id) == (span.trace_id, span.span_id)
    assert row.project == s.PROJECT
    assert (row.operation, row.provider) == ("chat", "openai")
    assert row.request_model == "gpt-4o-mini"
    assert row.response_model == "gpt-4o-mini-2024-07-18"
    assert row.api_base == "http://openai.test/v1/"
    assert row.response_id == "chatcmpl-123"
    assert row.started_at == span.start and row.ended_at == span.end
    assert row.latency_ms == round((span.end - span.start).total_seconds() * 1000)
    assert row.is_streaming is False
    assert (row.input_tokens, row.output_tokens, row.total_tokens) == (45, 8, 53)
    assert (row.cached_input_tokens, row.reasoning_tokens) == (10, 3)
    assert (row.status, row.error_type) == ("ok", None)
    assert row.finish_reasons == ["stop"]
    assert (row.temperature, row.max_tokens, row.top_p) == (0.2, 100, 0.9)
    assert (row.tools_offered, row.tool_calls_made) == (None, None)
    assert row.preview == [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "What's the weather in Paris?"},
        {"role": "assistant", "content": "Sunny, 22°C", "finish_reason": "stop"},
    ]

    trace = call.trace
    assert trace["schema_version"] == 1
    assert trace["volume"] == "alice-chat-42"
    assert trace["input_messages"] == row.preview[:2]
    assert trace["output_messages"] == row.preview[2:]
    assert trace["tokens"] == {
        "input": 45,
        "output": 8,
        "total": 53,
        "cached_input": 10,
        "reasoning": 3,
    }
    assert trace["raw_attributes"] == span.attributes
    assert trace["resource"]["service.name"] == s.PROJECT
    assert trace["project"] == s.PROJECT
    assert "app_name" not in trace


def test_tool_call_reply_is_mapped():
    (span,) = decoded(s.chat(reply=s.TOOL_CALL_REPLY, tools=[s.WEATHER_TOOL]))

    call = mapper.map_span(span)

    assert call.row.tools_offered == 1
    assert call.row.tool_calls_made == ["get_weather"]
    assert call.row.finish_reasons == ["tool_call"]
    (reply,) = call.trace["output_messages"]
    assert reply == {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}}],
        "finish_reason": "tool_call",
    }
    assert call.trace["tool_definitions"][0]["name"] == "get_weather"


def test_tool_round_trip_input_is_normalized():
    (span,) = decoded(s.chat(messages=s.TOOL_ROUND_TRIP, tools=[s.WEATHER_TOOL]))

    call = mapper.map_span(span)

    inputs = call.trace["input_messages"]
    assert [m["role"] for m in inputs] == ["system", "user", "assistant", "tool"]
    assert inputs[2]["tool_calls"][0]["name"] == "get_weather"
    assert inputs[3] == {"role": "tool", "content": '{"temp": 22}', "tool_call_id": "call_1"}
    assert [m["role"] for m in call.row.preview] == ["tool", "assistant"]


def test_error_span_is_mapped():
    (span,) = decoded(s.failing_chat())

    call = mapper.map_span(span)

    assert (call.row.status, call.row.error_type) == ("error", "RateLimitError")
    assert call.row.output_tokens is None
    assert "Rate limit" in call.trace["status_message"]
    assert call.trace["events"][0]["name"] == "exception"
    assert call.trace["output_messages"] == []


def test_span_without_volume_goes_to_default():
    (span,) = decoded(s.chat())

    assert mapper.map_span(span).row.volume == "default"


@pytest.mark.parametrize("bad_volume", ["", "   ", 42, "x" * 300])
def test_invalid_volume_falls_back_to_default(bad_volume):
    (span,) = decoded(s.chat())
    span = replace(span, attributes={**span.attributes, "aicontrol.volume": bad_volume})

    assert mapper.map_span(span).row.volume == "default"


def test_trace_and_step_names_are_mapped_and_calls_of_a_trace_share_its_id():
    spans = decoded(
        s.traced(
            "Summarize this PDF",
            ("extract key points", s.chat()),
            ("write summary", s.chat()),
        )
    )

    # the parent span opened by aicontrol.trace is not an LLM call
    llm_spans = [span for span in spans if mapper.is_llm_span(span)]
    rows = [mapper.map_span(span).row for span in llm_spans]

    assert [(r.trace_name, r.step_name) for r in rows] == [
        ("Summarize this PDF", "extract key points"),
        ("Summarize this PDF", "write summary"),
    ]
    assert rows[0].trace_id == rows[1].trace_id
    assert rows[0].span_id != rows[1].span_id
    trace = mapper.map_span(llm_spans[0]).trace
    assert (trace["trace_name"], trace["step_name"]) == ("Summarize this PDF", "extract key points")


def test_trace_and_step_names_are_none_when_not_set():
    (span,) = decoded(s.chat())

    call = mapper.map_span(span)

    assert (call.row.trace_name, call.row.step_name) == (None, None)
    assert (call.trace["trace_name"], call.trace["step_name"]) == (None, None)


def test_overlong_or_invalid_names_cannot_break_the_insert():
    (span,) = decoded(s.chat())
    attributes = {
        **span.attributes,
        "aicontrol.trace.name": "t" * 300,
        "aicontrol.step.name": 42,
    }

    row = mapper.map_span(replace(span, attributes=attributes)).row

    assert row.trace_name == "t" * mapper.MAX_NAME_LENGTH
    assert row.step_name is None


def test_the_project_is_read_from_the_resource_and_trimmed():
    (span,) = decoded(s.chat(), project="support-desk")

    assert mapper.map_span(span).row.project == "support-desk"
    padded = replace(span, resource={**span.resource, "aicontrol.project": "  support-desk "})
    assert mapper.map_span(padded).row.project == "support-desk"


@pytest.mark.parametrize("missing", [None, "", "   ", 42])
def test_a_span_without_a_usable_project_raises_no_project_error(missing):
    (span,) = decoded(s.chat())
    resource = {k: v for k, v in span.resource.items() if k != "aicontrol.project"}
    if missing is not None:
        resource["aicontrol.project"] = missing

    with pytest.raises(mapper.NoProjectError):
        mapper.map_span(replace(span, resource=resource))
    assert issubclass(mapper.NoProjectError, mapper.MappingError)


def test_non_llm_span_is_not_an_llm_span():
    (span,) = decoded(s.chat())
    other = replace(span, name="GET /", attributes={"http.method": "GET"})

    assert mapper.is_llm_span(span)
    assert not mapper.is_llm_span(other)


def test_invalid_messages_json_is_stored_empty_with_warning(caplog):
    (span,) = decoded(s.chat())
    span = replace(span, attributes={**span.attributes, "gen_ai.input.messages": "{broken"})

    with caplog.at_level(logging.WARNING):
        call = mapper.map_span(span)

    assert call.trace["input_messages"] == []
    assert call.trace["output_messages"]  # the rest of the call is still stored
    assert "invalid JSON in input messages" in caplog.text


@pytest.mark.parametrize("change", [{"span_id": "01"}, {"trace_id": ""}, {"start": None}])
def test_unstorable_span_raises_mapping_error(change):
    (span,) = decoded(s.chat())

    with pytest.raises(mapper.MappingError):
        mapper.map_span(replace(span, **change))


def test_unknown_parts_are_kept():
    message = {
        "role": "user",
        "parts": [
            {"type": "text", "content": "What is this?"},
            {"type": "image", "uri": "https://example.com/cat.png"},
        ],
    }

    assert mapper.normalize_message(message) == {
        "role": "user",
        "content": "What is this?",
        "parts": [{"type": "image", "uri": "https://example.com/cat.png"}],
    }
