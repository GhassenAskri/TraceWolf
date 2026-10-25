"""Heavy trace storage: one JSON document per LLM call, laid out by project and volume."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

MAX_PROJECT_NAME_LENGTH = 255
MAX_VOLUME_NAME_LENGTH = 255


class TraceNotFoundError(KeyError):
    pass


class TraceStore(Protocol):
    async def put(self, key: str, document: dict[str, Any]) -> int:
        """Store the document (overwriting any existing one) and return its size in bytes."""

    async def get(self, key: str) -> dict[str, Any]:
        """Return the document, or raise ``TraceNotFoundError``."""

    async def get_many(self, keys: list[str]) -> list[dict[str, Any]]:
        """Return the documents in the order of ``keys``."""

    async def list_prefix(self, prefix: str) -> list[str]:
        """Return every key starting with ``prefix``, sorted."""


def build_trace_key(
    project: str, volume: str, started_at: datetime, trace_id: str, span_id: str
) -> str:
    """``projects/{project}/volumes/{volume}/{YYYY}/{MM}/{DD}/{HHMMSS}_{trace}_{span}.json`` (UTC).

    Deterministic, so a retried span overwrites the same object. Calls stored before projects
    existed live under ``volumes/{volume}/...``; their rows keep that key, so they still load.
    """
    ts = started_at.astimezone(UTC)
    return f"{volume_prefix(project, volume)}{ts:%Y/%m/%d/%H%M%S}_{trace_id}_{span_id}.json"


def project_prefix(project: str) -> str:
    """Key prefix holding every trace of a project: ``projects/{project}/``."""
    return f"projects/{_segment(project, 'Project', MAX_PROJECT_NAME_LENGTH)}/"


def volume_prefix(project: str, volume: str) -> str:
    """Key prefix holding every trace of a volume: ``projects/{project}/volumes/{volume}/``."""
    segment = _segment(volume, "Volume", MAX_VOLUME_NAME_LENGTH)
    return f"{project_prefix(project)}volumes/{segment}/"


def _segment(name: str, what: str, max_length: int) -> str:
    """A project or volume name as one key segment.

    The name is percent-encoded so any name is accepted while keys stay inside their folder:
    ``alice-chat-42`` and ``user@example.com`` stay readable, ``a/b`` → ``a%2Fb``, spaces →
    ``%20``, and the dot-only names ``.``/``..`` → ``%2E``/``%2E%2E``.
    """
    if not name or len(name) > max_length:
        raise ValueError(f"{what} name must be 1-{max_length} characters")
    segment = quote(name, safe="-_~@:.")
    if set(segment) == {"."}:
        segment = segment.replace(".", "%2E")
    return segment


def serialize(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def deserialize(data: bytes) -> dict[str, Any]:
    return json.loads(data)
