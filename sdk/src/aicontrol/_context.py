"""Helpers to carry the current volume into threads.

Threads start with an empty context, so a volume set in the caller is lost unless the
context is copied. ``asyncio.to_thread`` already copies it; these helpers cover the rest.
"""

from __future__ import annotations

import contextvars
import functools
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, TypeVar

T = TypeVar("T")


def wrap_context(func: Callable[..., T]) -> Callable[..., T]:
    """Bind ``func`` to a copy of the current context (volume included).

    Use when handing work to a thread pool::

        pool.submit(aicontrol.wrap_context(work), arg)
    """
    ctx = contextvars.copy_context()

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return ctx.copy().run(func, *args, **kwargs)

    return wrapper


def run_in_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
    """Run ``func`` in a new daemon thread with the current context; returns a ``Future``."""
    future: Future[T] = Future()
    bound = wrap_context(func)

    def target() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(bound(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - forwarded to the caller via the future
            future.set_exception(exc)

    threading.Thread(target=target, name="aicontrol-worker", daemon=True).start()
    return future
