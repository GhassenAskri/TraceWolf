"""Decode OTLP/HTTP trace export requests (protobuf or JSON, optionally gzip) into plain spans."""

from __future__ import annotations

import base64
import gzip
import json
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from google.protobuf import json_format
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Status

PROTOBUF = "application/x-protobuf"
JSON = "application/json"


class OtlpDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class SpanEvent:
    name: str
    at: datetime | None
    attributes: dict[str, Any]


@dataclass(frozen=True)
class Span:
    trace_id: str
    span_id: str
    name: str
    start: datetime | None
    end: datetime | None
    status_code: str  # "unset" | "ok" | "error"
    status_message: str
    attributes: dict[str, Any]
    resource: dict[str, Any]
    scope: str
    events: list[SpanEvent] = field(default_factory=list)


def decode_request(body: bytes, content_type: str, content_encoding: str = "") -> list[Span]:
    """Turn an OTLP/HTTP request body into spans. Raises ``OtlpDecodeError`` on bad input."""
    body = _decompress(body, content_encoding)
    media_type = content_type.split(";")[0].strip().lower()
    request = ExportTraceServiceRequest()
    try:
        if media_type == JSON:
            json_format.ParseDict(
                _otlp_json_to_proto_json(json.loads(body)), request, ignore_unknown_fields=True
            )
        elif media_type in (PROTOBUF, ""):
            request.ParseFromString(body)
        else:
            raise OtlpDecodeError(f"Unsupported content type: {content_type!r}")
    except (
        DecodeError,
        json_format.ParseError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        if isinstance(exc, OtlpDecodeError):
            raise
        raise OtlpDecodeError(f"Cannot decode OTLP request: {exc}") from exc
    return list(_iter_spans(request))


def encode_response(content_type: str, rejected_spans: int = 0, error_message: str = "") -> bytes:
    response = ExportTraceServiceResponse()
    if rejected_spans:
        response.partial_success.rejected_spans = rejected_spans
        response.partial_success.error_message = error_message
    if content_type.split(";")[0].strip().lower() == JSON:
        return json.dumps(json_format.MessageToDict(response)).encode()
    return response.SerializeToString()


def _decompress(body: bytes, content_encoding: str) -> bytes:
    encoding = content_encoding.strip().lower()
    try:
        if encoding == "gzip":
            return gzip.decompress(body)
        if encoding == "deflate":
            return zlib.decompress(body)
    except (OSError, zlib.error) as exc:
        raise OtlpDecodeError(f"Cannot decompress {encoding} body: {exc}") from exc
    if encoding not in ("", "identity"):
        raise OtlpDecodeError(f"Unsupported content encoding: {content_encoding!r}")
    return body


def _otlp_json_to_proto_json(payload: Any) -> Any:
    """OTLP/JSON encodes trace/span ids as hex; protobuf's JSON mapping expects base64 bytes."""
    if not isinstance(payload, dict):
        raise OtlpDecodeError("OTLP JSON body must be an object")
    for resource_spans in payload.get("resourceSpans", []):
        for scope_spans in resource_spans.get("scopeSpans", []):
            for span in scope_spans.get("spans", []):
                for key in ("traceId", "spanId", "parentSpanId"):
                    if span.get(key):
                        span[key] = base64.b64encode(bytes.fromhex(span[key])).decode()
                for link in span.get("links", []):
                    for key in ("traceId", "spanId"):
                        if link.get(key):
                            link[key] = base64.b64encode(bytes.fromhex(link[key])).decode()
    return payload


_STATUS = {Status.STATUS_CODE_OK: "ok", Status.STATUS_CODE_ERROR: "error"}


def _iter_spans(request: ExportTraceServiceRequest):
    for resource_spans in request.resource_spans:
        resource = _attributes(resource_spans.resource.attributes)
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                yield Span(
                    trace_id=span.trace_id.hex(),
                    span_id=span.span_id.hex(),
                    name=span.name,
                    start=_time(span.start_time_unix_nano),
                    end=_time(span.end_time_unix_nano),
                    status_code=_STATUS.get(span.status.code, "unset"),
                    status_message=span.status.message,
                    attributes=_attributes(span.attributes),
                    resource=resource,
                    scope=scope_spans.scope.name,
                    events=[
                        SpanEvent(e.name, _time(e.time_unix_nano), _attributes(e.attributes))
                        for e in span.events
                    ],
                )


def _time(unix_nano: int) -> datetime | None:
    if not unix_nano:
        return None
    seconds, nanos = divmod(unix_nano, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=nanos // 1_000)


def _attributes(key_values) -> dict[str, Any]:
    return {kv.key: _value(kv.value) for kv in key_values}


def _value(value: AnyValue) -> Any:
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_value(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return _attributes(value.kvlist_value.values)
    if kind == "bytes_value":
        return base64.b64encode(value.bytes_value).decode()
    return getattr(value, kind)
