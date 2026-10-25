"""OTLP/HTTP trace receiver: `POST /v1/traces`."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository as repo
from app.deps import get_session, get_store
from app.ingest import mapper, otlp
from app.services.calls import CallToStore, store_calls
from app.storage.base import TraceStore

logger = logging.getLogger(__name__)

router = APIRouter()

ERROR_HEADER = "X-AIControl-Error"  # tells the SDK why calls were refused
PROJECT_NOT_FOUND = "project-not-found"
PROJECT_MISSING = "project-missing"


@router.post("/v1/traces")
async def ingest_traces(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[TraceStore, Depends(get_store)],
) -> Response:
    """Store the LLM-call spans of an OTLP export request.

    - Non-LLM spans are ignored.
    - Calls are only accepted for a project that exists (projects are created in the web UI):
      if none of the LLM spans is accepted because their project does not exist → 404, because
      they carry no project at all → 400 (both with an `X-AIControl-Error` header and a message,
      and not retried by exporters). If only some are refused, the others are stored and the
      refused ones are reported in `partial_success`.
    - Malformed LLM spans are skipped and reported as `partial_success.rejected_spans`.
    - Undecodable bodies → 400 (not retried by exporters).
    - Storage failures → 503, so the exporter retries the whole batch (storage is idempotent).
    """
    content_type = request.headers.get("content-type", otlp.PROTOBUF)
    media_type = otlp.JSON if content_type.startswith(otlp.JSON) else otlp.PROTOBUF
    try:
        spans = otlp.decode_request(
            await request.body(), content_type, request.headers.get("content-encoding", "")
        )
    except otlp.OtlpDecodeError as exc:
        logger.warning("Rejected OTLP request: %s", exc)
        return Response(str(exc), status_code=400, media_type="text/plain")

    mapped: list[CallToStore] = []
    rejected: list[str] = []
    without_project: list[str] = []
    for span in spans:
        if not mapper.is_llm_span(span):
            continue
        try:
            mapped.append(mapper.map_span(span))
        except mapper.NoProjectError as exc:
            without_project.append(span.span_id)
            rejected.append(f"{span.span_id}: {exc}")
        except Exception as exc:  # noqa: BLE001 - one bad span must not drop the batch
            logger.warning("Skipping span %s: %s", span.span_id, exc)
            rejected.append(f"{span.span_id}: {exc}")

    known = await repo.existing_project_slugs(session, {c.row.project for c in mapped})
    calls = [c for c in mapped if c.row.project in known]
    unknown = sorted({c.row.project for c in mapped} - known)
    for call in mapped:
        if call.row.project not in known:
            rejected.append(f"{call.row.span_id}: project {call.row.project!r} not found")

    if not calls and unknown:
        logger.warning("Rejected calls for unknown project(s) %s", unknown)
        return _refusal(404, PROJECT_NOT_FOUND, _not_found_message(unknown))
    if not calls and without_project:
        return _refusal(400, PROJECT_MISSING, MISSING_MESSAGE)

    try:
        await store_calls(session, store, calls)
    except Exception:
        logger.exception("Failed to store %d LLM calls; asking the exporter to retry", len(calls))
        return Response("Storage unavailable", status_code=503, media_type="text/plain")

    body = otlp.encode_response(media_type, len(rejected), "; ".join(rejected)[:1000])
    return Response(body, media_type=media_type)


MISSING_MESSAGE = (
    "These calls carry no project. Upgrade the aicontrol SDK and call "
    'aicontrol.init(project="my-project") with the slug of your project (or set AICONTROL_PROJECT).'
)


def _not_found_message(slugs: list[str]) -> str:
    quoted = ", ".join(repr(s) for s in slugs)
    noun = "Project" if len(slugs) == 1 else "Projects"
    return (
        f"{noun} {quoted} not found. The SDK takes the slug of a project (shown on its page in the "
        "AIControl UI), not its name. Create the project there first if it does not exist."
    )


def _refusal(status: int, reason: str, message: str) -> Response:
    return Response(
        message, status_code=status, media_type="text/plain", headers={ERROR_HEADER: reason}
    )
