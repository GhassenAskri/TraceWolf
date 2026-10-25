"""Hook LLM client libraries so their calls become spans on the SDK's current tracer provider.

Instrumentors are installed once per process against a delegating tracer provider that
forwards every span to whichever SDK provider is active (or drops it after ``shutdown()``).
This avoids relying on ``uninstrument()``, which does not unwrap ``openai`` 3.x in
opentelemetry-instrumentation-openai 0.62.x (its dotted ``"Completions.create"`` attribute
paths are not resolved by ``opentelemetry.instrumentation.utils.unwrap``), so repeated
instrument/uninstrument cycles would stack wrappers.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
from collections.abc import Callable

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger("aicontrol")

ProviderGetter = Callable[[], TracerProvider | None]

_lock = threading.Lock()
_instrumented = False


def instrument(get_provider: ProviderGetter) -> None:
    """Instrument the OpenAI client (once per process) if it is installed.

    Message content is captured by default; set ``TRACELOOP_TRACE_CONTENT=false`` to record
    only metadata (models, tokens, timings, finish reasons).
    """
    global _instrumented
    with _lock:
        if _instrumented:
            return
        if importlib.util.find_spec("openai") is None:
            logger.warning(
                "aicontrol: `openai` is not installed; OpenAI calls will not be captured"
            )
            return

        from opentelemetry.instrumentation.openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument(tracer_provider=_DelegatingTracerProvider(get_provider))
        _instrumented = True


class _DelegatingTracerProvider(trace.TracerProvider):
    def __init__(self, get_provider: ProviderGetter) -> None:
        self._get_provider = get_provider

    def get_tracer(self, instrumenting_module_name, *args, **kwargs) -> trace.Tracer:
        return _DelegatingTracer(self._get_provider, instrumenting_module_name, args, kwargs)


class _DelegatingTracer(trace.Tracer):
    """Resolves the SDK's current provider on every span, so re-``init()`` just works."""

    def __init__(self, get_provider: ProviderGetter, name: str, args: tuple, kwargs: dict):
        self._get_provider = get_provider
        self._name, self._args, self._kwargs = name, args, kwargs
        self._cached: tuple[TracerProvider, trace.Tracer] | None = None

    def _tracer(self) -> trace.Tracer:
        provider = self._get_provider()
        if provider is None:
            return trace.NoOpTracer()
        cached = self._cached
        if cached is None or cached[0] is not provider:
            cached = (provider, provider.get_tracer(self._name, *self._args, **self._kwargs))
            self._cached = cached
        return cached[1]

    def start_span(self, *args, **kwargs) -> trace.Span:
        return self._tracer().start_span(*args, **kwargs)

    def start_as_current_span(self, *args, **kwargs):
        return self._tracer().start_as_current_span(*args, **kwargs)
