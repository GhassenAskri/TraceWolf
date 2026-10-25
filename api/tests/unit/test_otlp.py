import gzip
from datetime import UTC, datetime

import pytest
from google.protobuf import json_format
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from app.ingest import otlp
from tests import spans as s


@pytest.fixture(scope="module")
def captured():
    return s.capture(s.chat(volume="alice-chat-42"), s.failing_chat())


def test_protobuf_request_is_decoded_to_spans(captured):
    decoded = otlp.decode_request(s.to_protobuf(captured), otlp.PROTOBUF)

    assert [d.name for d in decoded] == ["openai.chat", "openai.chat"]
    ok, failed = decoded
    original = captured[0]
    assert ok.trace_id == format(original.context.trace_id, "032x")
    assert ok.span_id == format(original.context.span_id, "016x")
    assert ok.attributes["aicontrol.volume"] == "alice-chat-42"
    assert ok.attributes["gen_ai.usage.input_tokens"] == 45
    assert ok.attributes["gen_ai.response.finish_reasons"] == ["stop"]
    assert ok.resource["service.name"] == s.PROJECT
    assert ok.resource["aicontrol.project"] == s.PROJECT
    assert ok.status_code in ("ok", "unset")
    assert failed.status_code == "error"
    assert "Rate limit" in failed.status_message
    assert [e.name for e in failed.events] == ["exception"]


def test_timestamps_keep_microseconds(captured):
    (ok, _) = otlp.decode_request(s.to_protobuf(captured), otlp.PROTOBUF)
    expected = captured[0].start_time // 1_000

    assert ok.start.tzinfo is UTC
    assert int(ok.start.timestamp()) * 1_000_000 + ok.start.microsecond == expected
    assert ok.end > ok.start


def test_json_request_decodes_like_protobuf(captured):
    from_json = otlp.decode_request(s.to_otlp_json(captured), "application/json; charset=utf-8")
    from_proto = otlp.decode_request(s.to_protobuf(captured), otlp.PROTOBUF)

    assert from_json == from_proto


def test_gzip_body_is_accepted(captured):
    body = gzip.compress(s.to_protobuf(captured))

    assert len(otlp.decode_request(body, otlp.PROTOBUF, "gzip")) == 2


@pytest.mark.parametrize(
    ("body", "content_type", "encoding"),
    [
        (b"\xff\xff\xff", otlp.PROTOBUF, ""),
        (b"{not json", otlp.JSON, ""),
        (b"[]", otlp.JSON, ""),
        (b"x", "text/plain", ""),
        (b"not gzip", otlp.PROTOBUF, "gzip"),
        (b"", otlp.PROTOBUF, "br"),
    ],
)
def test_bad_requests_raise_decode_error(body, content_type, encoding):
    with pytest.raises(otlp.OtlpDecodeError):
        otlp.decode_request(body, content_type, encoding)


def test_empty_request_has_no_spans():
    assert otlp.decode_request(b"", otlp.PROTOBUF) == []


def test_attribute_value_types():
    request = json_format.ParseDict(
        {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "S/kvNXezTaajzpKdDg5HNg==",
                                    "spanId": "APBnqgupArc=",
                                    "name": "x",
                                    "startTimeUnixNano": "1790000000123456789",
                                    "attributes": [
                                        {"key": "s", "value": {"stringValue": "a"}},
                                        {"key": "b", "value": {"boolValue": True}},
                                        {"key": "i", "value": {"intValue": "7"}},
                                        {"key": "d", "value": {"doubleValue": 0.5}},
                                        {
                                            "key": "arr",
                                            "value": {
                                                "arrayValue": {"values": [{"stringValue": "x"}]}
                                            },
                                        },
                                        {
                                            "key": "kv",
                                            "value": {
                                                "kvlistValue": {
                                                    "values": [
                                                        {"key": "k", "value": {"intValue": "1"}}
                                                    ]
                                                }
                                            },
                                        },
                                        {"key": "empty", "value": {}},
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        ExportTraceServiceRequest(),
    )

    (span,) = otlp.decode_request(request.SerializeToString(), otlp.PROTOBUF)

    assert span.attributes == {
        "s": "a",
        "b": True,
        "i": 7,
        "d": 0.5,
        "arr": ["x"],
        "kv": {"k": 1},
        "empty": None,
    }
    assert span.start == datetime(2026, 9, 21, 14, 13, 20, 123456, tzinfo=UTC)
    assert span.end is None


def test_response_encoding_reports_partial_success():
    body = otlp.encode_response(otlp.PROTOBUF, rejected_spans=2, error_message="bad")
    response = ExportTraceServiceResponse.FromString(body)

    assert response.partial_success.rejected_spans == 2
    assert otlp.encode_response(otlp.JSON) == b"{}"
