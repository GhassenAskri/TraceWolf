"""AIControl SDK: capture LLM calls with OpenTelemetry and send them to the AIControl API."""

from aicontrol._config import SDK_VERSION, flush, init, shutdown
from aicontrol._context import run_in_thread, wrap_context
from aicontrol._trace import current_step_name, current_trace_name, step, trace
from aicontrol._volume import DEFAULT_VOLUME, current_volume, reset_volume, set_volume, volume

__version__ = SDK_VERSION

__all__ = [
    "DEFAULT_VOLUME",
    "current_step_name",
    "current_trace_name",
    "current_volume",
    "flush",
    "init",
    "reset_volume",
    "run_in_thread",
    "set_volume",
    "shutdown",
    "step",
    "trace",
    "volume",
    "wrap_context",
]
