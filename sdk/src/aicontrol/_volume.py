"""Volume selection: which storage volume the LLM calls made in the current context belong to.

The current volume lives in a ``contextvar``, so it is isolated per asyncio task and per
request, and restored automatically when a ``volume`` block exits.
"""

from __future__ import annotations

import functools
import inspect
from contextvars import ContextVar, Token
from typing import Any

DEFAULT_VOLUME = "default"
VOLUME_ATTRIBUTE = "aicontrol.volume"

_current_volume: ContextVar[str | None] = ContextVar("aicontrol_volume", default=None)


def current_volume() -> str:
    """Return the volume for the current context, or ``"default"`` if none is set."""
    return _current_volume.get() or DEFAULT_VOLUME


def set_volume(name: str) -> Token[str | None]:
    """Set the volume for the rest of the current context (e.g. in a web request middleware).

    Returns a token that can be passed to ``reset_volume`` to restore the previous value.
    """
    return _current_volume.set(_validate(name))


def reset_volume(token: Token[str | None]) -> None:
    """Restore the volume that was active before the matching ``set_volume`` call."""
    _current_volume.reset(token)


class volume:  # noqa: N801 - used like a function: `with aicontrol.volume("x"):`
    """Send the LLM calls made inside a block or function to a named volume.

    Usable as a sync/async context manager and as a sync/async decorator::

        with aicontrol.volume("alice-chat-42"):
            ollama.chat(...)

        @aicontrol.volume("support")
        async def reply(msg): ...
    """

    def __init__(self, name: str) -> None:
        self.name = _validate(name)
        self._tokens: list[Token[str | None]] = []

    def __enter__(self) -> volume:
        self._tokens.append(_current_volume.set(self.name))
        return self

    def __exit__(self, *exc_info: object) -> None:
        _current_volume.reset(self._tokens.pop())

    async def __aenter__(self) -> volume:
        return self.__enter__()

    async def __aexit__(self, *exc_info: object) -> None:
        self.__exit__(*exc_info)

    def __call__(self, func: Any) -> Any:
        # Each call gets its own scope, so one decorated function can run concurrently.
        name = self.name
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with volume(name):
                    return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with volume(name):
                return func(*args, **kwargs)

        return wrapper


def _validate(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Volume name must be a non-empty string, got {name!r}")
    return name
