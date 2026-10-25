"""SDK setup: project, tracer provider, volume processor and exporter to the AIControl API."""

from __future__ import annotations

import atexit
import logging
import os
import re
import threading

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter

from aicontrol import _instrument
from aicontrol._processor import VolumeSpanProcessor
from aicontrol._project_check import ProjectMonitor

logger = logging.getLogger("aicontrol")

DEFAULT_ENDPOINT = "http://localhost:8000"
SDK_VERSION = "0.1.0"

PROJECT_ENV = "AICONTROL_PROJECT"
ENDPOINT_ENV = "AICONTROL_ENDPOINT"
PROJECT_ATTRIBUTE = "aicontrol.project"
MAX_SLUG_LENGTH = 64  # same limit as the API
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_lock = threading.Lock()
_provider: TracerProvider | None = None
_monitor: ProjectMonitor | None = None
_atexit_registered = False


def init(
    *,
    project: str | None = None,
    endpoint: str | None = None,
    span_exporter: SpanExporter | None = None,
    batch: bool = True,
    instrument: bool = True,
) -> TracerProvider:
    """Initialise the SDK. Safe to call more than once: later calls are ignored.

    Args:
        project: The slug of the AIControl project the calls belong to, e.g. ``"support-desk"``
            (shown on the project's page in the AIControl UI; it is generated from the name when
            the project is created, and is not the name). Required: pass it here or set the
            ``AICONTROL_PROJECT`` environment variable. The project must exist in AIControl;
            calls for an unknown project are rejected.
        endpoint: Base URL of the AIControl API; spans are sent to ``{endpoint}/v1/traces``.
            Defaults to ``AICONTROL_ENDPOINT``, else ``http://localhost:8000``.
        span_exporter: Override the OTLP exporter (mainly for tests).
        batch: Export in the background in batches (default). ``False`` exports synchronously.
        instrument: Hook the OpenAI client so its calls are captured (default).

    All arguments are keyword-only. Raises ``ValueError`` if the project is missing or invalid.
    The SDK uses its own tracer provider and does not replace the application's global one.
    """
    global _provider, _monitor, _atexit_registered
    with _lock:
        if _provider is not None:
            logger.warning("aicontrol is already initialised; ignoring this init() call")
            return _provider

        project = resolve_project(project)
        resource = Resource.create(
            {
                SERVICE_NAME: project,
                PROJECT_ATTRIBUTE: project,
                "aicontrol.sdk.version": SDK_VERSION,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(VolumeSpanProcessor())
        monitor = None
        if span_exporter is None:
            base_url = resolve_endpoint(endpoint)
            monitor = ProjectMonitor(project, base_url)
            exporter = OTLPSpanExporter(endpoint=traces_url(base_url), session=monitor.session())
        else:
            exporter = span_exporter
        processor = BatchSpanProcessor(exporter) if batch else SimpleSpanProcessor(exporter)
        provider.add_span_processor(processor)
        _provider = provider
        _monitor = monitor
        if monitor is not None:
            monitor.start()  # a background check: init() never waits for the API
        if instrument:
            _instrument.instrument(get_tracer_provider)

        if not _atexit_registered:
            atexit.register(shutdown)
            _atexit_registered = True
        return provider


def resolve_project(project: str | None) -> str:
    """The project slug: the argument, else ``AICONTROL_PROJECT``; trimmed and validated.

    Raises ``ValueError`` when there is none or it is not a slug (a mistake in the code or the
    deployment, so it is reported at startup, unlike an unreachable API, which never is).
    """
    given = project is not None
    candidate = project if given else os.environ.get(PROJECT_ENV)
    if candidate is None or candidate == "":
        raise ValueError(
            'aicontrol.init() needs a project: pass project="my-project" (the slug of the project, '
            f"shown in the AIControl UI) or set the {PROJECT_ENV} environment variable"
        )
    source = "project=" if given else PROJECT_ENV
    if not isinstance(candidate, str):
        raise ValueError(f"Invalid project ({source}): must be a string, got {candidate!r}")
    slug = candidate.strip()
    if not slug:
        raise ValueError(f"Invalid project ({source}): must not be blank")
    if len(slug) > MAX_SLUG_LENGTH or _SLUG.fullmatch(slug) is None:
        guess = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
        hint = (
            f" Did you mean {guess!r}? Check it on the project's page."
            if guess and guess != slug and _SLUG.fullmatch(guess) and len(guess) <= MAX_SLUG_LENGTH
            else ""
        )
        raise ValueError(
            f"Invalid project ({source}): {slug!r} is not a slug. Pass the slug of the project, "
            "shown on its page in the AIControl UI (lowercase letters, digits and single hyphens, "
            f"at most {MAX_SLUG_LENGTH} characters, for example 'support-desk').{hint}"
        )
    return slug


def resolve_endpoint(endpoint: str | None) -> str:
    """The API base URL: the argument, else ``AICONTROL_ENDPOINT``, else the default."""
    return endpoint or os.environ.get(ENDPOINT_ENV) or DEFAULT_ENDPOINT


def get_tracer_provider() -> TracerProvider | None:
    """The SDK's tracer provider, or ``None`` before ``init()``."""
    return _provider


def flush(timeout_millis: int = 30_000) -> bool:
    """Send pending spans now. Returns ``False`` on timeout or if the SDK is not initialised."""
    provider = _provider
    return provider.force_flush(timeout_millis) if provider else False


def shutdown() -> None:
    """Flush pending spans and stop the SDK. ``init()`` can be called again afterwards."""
    global _provider, _monitor
    with _lock:
        provider, _provider = _provider, None
        monitor, _monitor = _monitor, None
    if provider is not None:
        provider.shutdown()
    if monitor is not None:
        monitor.close()


def traces_url(endpoint: str) -> str:
    return endpoint.rstrip("/") + "/v1/traces"
