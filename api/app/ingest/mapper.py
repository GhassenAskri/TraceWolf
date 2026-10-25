"""Map an OTLP span of an LLM call to its S3 trace document and its Postgres index row.

Understands the GenAI semantic-convention attributes emitted by OpenLLMetry's OpenAI
instrumentor: `gen_ai.input.messages` / `gen_ai.output.messages` (JSON lists of
`{role, parts}`), `gen_ai.tool.definitions`, `gen_ai.usage.*`, `gen_ai.request.*`, ...
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.ingest.otlp import Span
from app.repository import NewCall
from app.services.calls import CallToStore
from app.storage.base import MAX_VOLUME_NAME_LENGTH
from app.views import new_messages

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_VOLUME = "default"
VOLUME_ATTRIBUTE = "aicontrol.volume"
PROJECT_ATTRIBUTE = "aicontrol.project"  # a resource attribute: one project per process
TRACE_NAME_ATTRIBUTE = "aicontrol.trace.name"
STEP_NAME_ATTRIBUTE = "aicontrol.step.name"
MAX_NAME_LENGTH = 255  # width of the trace_name / step_name columns
LLM_MARKERS = ("gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model")


class MappingError(ValueError):
    """The span is an LLM call but cannot be stored (e.g. missing ids or timestamps)."""


class NoProjectError(MappingError):
    """The span carries no project (it comes from an SDK that predates projects)."""


def is_llm_span(span: Span) -> bool:
    return any(key in span.attributes for key in LLM_MARKERS)


def map_span(span: Span) -> CallToStore:
    if len(span.trace_id) != 32 or len(span.span_id) != 16:
        raise MappingError(f"Invalid trace/span id: {span.trace_id!r}/{span.span_id!r}")
    if span.start is None:
        raise MappingError(f"Span {span.span_id} has no start time")

    a = span.attributes
    project = _project(span.resource.get(PROJECT_ATTRIBUTE))
    volume = _volume(a.get(VOLUME_ATTRIBUTE))
    input_messages = _messages(a.get("gen_ai.input.messages"), span, "input")
    output_messages = _messages(a.get("gen_ai.output.messages"), span, "output")
    tool_definitions = _json(a.get("gen_ai.tool.definitions"), span, "tool definitions")
    tool_calls_made = [t["name"] for m in output_messages for t in m.get("tool_calls", [])]
    latency_ms = (
        round((span.end - span.start).total_seconds() * 1000) if span.end is not None else None
    )
    status = "error" if span.status_code == "error" else "ok"
    finish_reasons = _str_list(a.get("gen_ai.response.finish_reasons"))

    row = NewCall(
        project=project,
        volume=volume,
        trace_id=span.trace_id,
        span_id=span.span_id,
        started_at=span.start,
        ended_at=span.end,
        trace_key="",  # derived by store_calls()
        trace_name=_name(a.get(TRACE_NAME_ATTRIBUTE)),
        step_name=_name(a.get(STEP_NAME_ATTRIBUTE)),
        operation=_str(a.get("gen_ai.operation.name")),
        provider=_str(a.get("gen_ai.provider.name")),
        request_model=_str(a.get("gen_ai.request.model")),
        response_model=_str(a.get("gen_ai.response.model")),
        api_base=_str(a.get("gen_ai.openai.api_base")),
        response_id=_str(a.get("gen_ai.response.id")),
        latency_ms=latency_ms,
        is_streaming=_bool(a.get("gen_ai.is_streaming")),
        input_tokens=_int(a.get("gen_ai.usage.input_tokens")),
        output_tokens=_int(a.get("gen_ai.usage.output_tokens")),
        total_tokens=_int(a.get("gen_ai.usage.total_tokens")),
        cached_input_tokens=_int(a.get("gen_ai.usage.cache_read.input_tokens")),
        reasoning_tokens=_int(a.get("gen_ai.usage.reasoning_tokens")),
        status=status,
        error_type=_str(a.get("error.type")),
        finish_reasons=finish_reasons,
        temperature=_float(a.get("gen_ai.request.temperature")),
        max_tokens=_int(a.get("gen_ai.request.max_tokens")),
        top_p=_float(a.get("gen_ai.request.top_p")),
        tools_offered=len(tool_definitions) if isinstance(tool_definitions, list) else None,
        tool_calls_made=tool_calls_made or None,
        preview=new_messages(input_messages, output_messages),
    )
    trace = {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "volume": volume,
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "span_name": span.name,
        "scope": span.scope,
        "trace_name": row.trace_name,
        "step_name": row.step_name,
        "started_at": span.start.isoformat(),
        "ended_at": span.end.isoformat() if span.end else None,
        "latency_ms": latency_ms,
        "status": status,
        "status_message": span.status_message or None,
        "error_type": row.error_type,
        "operation": row.operation,
        "provider": row.provider,
        "request_model": row.request_model,
        "response_model": row.response_model,
        "api_base": row.api_base,
        "response_id": row.response_id,
        "streaming": row.is_streaming,
        "request": {
            "temperature": row.temperature,
            "max_tokens": row.max_tokens,
            "top_p": row.top_p,
        },
        "tokens": {
            "input": row.input_tokens,
            "output": row.output_tokens,
            "total": row.total_tokens,
            "cached_input": row.cached_input_tokens,
            "reasoning": row.reasoning_tokens,
        },
        "finish_reasons": finish_reasons,
        "input_messages": input_messages,
        "output_messages": output_messages,
        "tool_definitions": tool_definitions,
        "events": [
            {"name": e.name, "at": e.at.isoformat() if e.at else None, "attributes": e.attributes}
            for e in span.events
        ],
        "raw_attributes": a,
        "resource": span.resource,
    }
    return CallToStore(row=row, trace=trace)


def normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    """`{role, parts}` → `{role, content, tool_calls?, tool_call_id?, finish_reason?, parts?}`.

    `text` parts become `content`, `tool_call` parts `tool_calls`, a `tool_call_response` part
    becomes the tool message's `content` + `tool_call_id`. Unknown part types are kept in
    `parts` so nothing is lost.
    """
    texts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    other_parts: list[Any] = []
    tool_call_id = None
    for part in message.get("parts") or []:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind == "text":
            texts.append(str(part.get("content", "")))
        elif kind == "tool_call":
            tool_calls.append(
                {"id": part.get("id"), "name": part.get("name"), "arguments": part.get("arguments")}
            )
        elif kind == "tool_call_response":
            tool_call_id = part.get("id")
            response = part.get("response")
            texts.append(response if isinstance(response, str) else json.dumps(response))
        else:
            other_parts.append(part)

    normalized: dict[str, Any] = {
        "role": message.get("role"),
        "content": "".join(texts) if texts else None,
    }
    if tool_calls:
        normalized["tool_calls"] = tool_calls
    if tool_call_id is not None:
        normalized["tool_call_id"] = tool_call_id
    if message.get("finish_reason"):
        normalized["finish_reason"] = message["finish_reason"]
    if other_parts:
        normalized["parts"] = other_parts
    return normalized


def _messages(raw: Any, span: Span, which: str) -> list[dict[str, Any]]:
    parsed = _json(raw, span, f"{which} messages")
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        logger.warning("Span %s: %s messages are not a list; storing none", span.span_id, which)
        return []
    return [normalize_message(m) for m in parsed if isinstance(m, dict)]


def _json(raw: Any, span: Span, what: str) -> Any:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Span %s: invalid JSON in %s; storing none", span.span_id, what)
        return None


def _volume(value: Any) -> str:
    if isinstance(value, str) and value.strip() and len(value) <= MAX_VOLUME_NAME_LENGTH:
        return value
    if value is not None:
        logger.warning("Invalid volume %r; using %r", value, DEFAULT_VOLUME)
    return DEFAULT_VOLUME


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _project(value: Any) -> str:
    """The project slug sent by the SDK (trimmed). Whether it exists is checked by the route."""
    if not isinstance(value, str) or not value.strip():
        raise NoProjectError(f"Span has no {PROJECT_ATTRIBUTE} resource attribute")
    return value.strip()


def _name(value: Any) -> str | None:
    """A name chosen by the application, cut to the column width so a long one cannot fail the
    insert (and with it the whole batch)."""
    text = _str(value)
    return text[:MAX_NAME_LENGTH] if text else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _str_list(value: Any) -> list[str] | None:
    if isinstance(value, list | tuple):
        return [str(v) for v in value] or None
    if isinstance(value, str):
        return [value]
    return None
