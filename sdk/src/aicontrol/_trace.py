"""Trace and step names: group the LLM calls of one piece of work and label each of them.

``trace`` opens a real parent span, so every call made inside it shares one trace id. ``step``
only labels. Both names live in context variables, like the volume, and are stamped on every span
when it starts (see ``VolumeSpanProcessor``), so the application never passes them to its LLM
client. The API stores them with each call and the web UI draws the trace as a tree.
"""

from __future__ import annotations

import functools
import inspect
from contextvars import ContextVar, Token
from typing import Any

TRACE_NAME_ATTRIBUTE = "aicontrol.trace.name"
STEP_NAME_ATTRIBUTE = "aicontrol.step.name"

_current_trace_name: ContextVar[str | None] = ContextVar("aicontrol_trace_name", default=None)
_current_step_name: ContextVar[str | None] = ContextVar("aicontrol_step_name", default=None)


def current_trace_name() -> str | None:
    """Return the name of the innermost ``trace`` block of the current context, if any."""
    return _current_trace_name.get()


def current_step_name() -> str | None:
    """Return the name of the innermost ``step`` block of the current context, if any."""
    return _current_step_name.get()


class _Scope:
    """A name that applies to a block or a function call; subclasses define what it does."""

    def __init__(self, name: str) -> None:
        self.name = _validate(name)

    def __enter__(self) -> _Scope:
        raise NotImplementedError

    def __exit__(self, *exc_info: object) -> None:
        raise NotImplementedError

    async def __aenter__(self) -> _Scope:
        return self.__enter__()

    async def __aexit__(self, *exc_info: object) -> None:
        self.__exit__(*exc_info)

    def __call__(self, func: Any) -> Any:
        # Each call gets its own scope, so one decorated function can run concurrently.
        name, scope = self.name, type(self)
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with scope(name):
                    return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with scope(name):
                return func(*args, **kwargs)

        return wrapper


class trace(_Scope):  # noqa: N801 - used like a function: `with aicontrol.trace("x"):`
    """Make the LLM calls made inside a block or function one named trace.

    A real parent span is opened, so all the calls share a trace id and the web UI shows them
    as one tree under this name. Blocks nest: a ``trace`` inside another is a child span of it
    and its name applies to the calls made inside it. Usable as a sync/async context manager and
    as a sync/async decorator::

        with aicontrol.trace("Summarize this PDF"):
            with aicontrol.step("extract key points"):
                client.chat.completions.create(...)
            with aicontrol.step("write summary"):
                client.chat.completions.create(...)

        @aicontrol.trace("Summarize this PDF")
        async def summarize(pdf): ...

    Does nothing (but still names the calls) before ``aicontrol.init()``.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._scopes: list[tuple[Token[str | None], Any]] = []

    def __enter__(self) -> trace:
        # Imported here: `_config` imports the span processor, which imports this module.
        from aicontrol._config import get_tracer_provider

        # The name is set first so that the parent span itself is stamped with it too.
        token = _current_trace_name.set(self.name)
        provider = get_tracer_provider()
        span = (
            provider.get_tracer("aicontrol").start_as_current_span(self.name) if provider else None
        )
        if span is not None:
            span.__enter__()
        self._scopes.append((token, span))
        return self

    def __exit__(self, *exc_info: object) -> None:
        token, span = self._scopes.pop()
        try:
            if span is not None:
                span.__exit__(*exc_info)  # records the exception on the span, if any
        finally:
            _current_trace_name.reset(token)


class step(_Scope):  # noqa: N801 - used like a function: `with aicontrol.step("x"):`
    """Label the LLM calls made inside a block or function with a step name.

    Opens no span: it only names the calls. Use it inside ``aicontrol.trace`` so that the steps
    of one piece of work are shown together. Usable as a sync/async context manager and as a
    sync/async decorator::

        with aicontrol.step("translate to French"):
            client.chat.completions.create(...)

        @aicontrol.step("write summary")
        def write_summary(text): ...
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._tokens: list[Token[str | None]] = []

    def __enter__(self) -> step:
        self._tokens.append(_current_step_name.set(self.name))
        return self

    def __exit__(self, *exc_info: object) -> None:
        _current_step_name.reset(self._tokens.pop())


def _validate(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Name must be a non-empty string, got {name!r}")
    return name
