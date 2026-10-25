"""How calls are presented: which messages are new in a call, transcript formatting."""

from __future__ import annotations

import json
from typing import Any


def new_messages(
    input_messages: list[dict[str, Any]], output_messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The part of a call that is new: input after the last assistant message, plus the output.

    Every call re-sends the whole history, so this is what the timeline shows per call:
    first turn → system + user + reply; turn N → latest user message + reply;
    tool round-trip → tool result(s) + reply.
    """
    last_assistant = max(
        (i for i, m in enumerate(input_messages) if m.get("role") == "assistant"), default=-1
    )
    return [*input_messages[last_assistant + 1 :], *output_messages]


def format_transcript(project: str, volume: str, until: str, calls: list[dict[str, Any]]) -> str:
    """Plain-text transcript of an exported volume: each call's new messages, oldest first."""
    lines = [
        f"# Project: {project}",
        f"# Volume: {volume}",
        f"# {len(calls)} calls up to {until}",
        "",
    ]
    for number, call in enumerate(calls, start=1):
        tokens = call.get("tokens") or {}
        model = call.get("response_model") or call.get("request_model") or "unknown model"
        lines.append(
            f"## Call {number} (id {call.get('id')}) | {call.get('started_at')} | {model} | "
            f"tokens {tokens.get('input')} in / {tokens.get('output')} out | {call.get('status')}"
        )
        if call.get("error_type"):
            lines.append(f"[error] {call['error_type']}: {call.get('status_message') or ''}")
        messages = new_messages(call.get("input_messages") or [], call.get("output_messages") or [])
        lines += [_format_message(m) for m in messages]
        lines.append("")
    return "\n".join(lines)


def _format_message(message: dict[str, Any]) -> str:
    role = message.get("role") or "unknown"
    parts = []
    if message.get("content"):
        label = f"tool {message['tool_call_id']}" if message.get("tool_call_id") else role
        parts.append(f"[{label}] {message['content']}")
    for call in message.get("tool_calls") or []:
        arguments = json.dumps(call.get("arguments"), ensure_ascii=False)
        parts.append(f"[{role} -> tool call {call.get('id')}] {call.get('name')}({arguments})")
    return "\n".join(parts) if parts else f"[{role}] (empty)"
