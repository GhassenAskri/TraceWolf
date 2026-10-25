from __future__ import annotations

from opentelemetry.context import Context
from opentelemetry.sdk.trace import Span, SpanProcessor

from aicontrol._trace import (
    STEP_NAME_ATTRIBUTE,
    TRACE_NAME_ATTRIBUTE,
    current_step_name,
    current_trace_name,
)
from aicontrol._volume import VOLUME_ATTRIBUTE, current_volume


class VolumeSpanProcessor(SpanProcessor):
    """Stamps the current volume, trace name and step name on every span when it starts.

    Runs for spans created by any instrumentation (e.g. OpenLLMetry's Ollama spans),
    so the application never has to pass them to its LLM client. The trace and step names are
    only stamped when set (see ``aicontrol.trace`` and ``aicontrol.step``).
    """

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        span.set_attribute(VOLUME_ATTRIBUTE, current_volume())
        if (trace_name := current_trace_name()) is not None:
            span.set_attribute(TRACE_NAME_ATTRIBUTE, trace_name)
        if (step_name := current_step_name()) is not None:
            span.set_attribute(STEP_NAME_ATTRIBUTE, step_name)
