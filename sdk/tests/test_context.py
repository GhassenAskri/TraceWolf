import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import aicontrol
from tests.conftest import volumes_by_span_name


def test_plain_thread_does_not_inherit_volume(tracer, exporter):
    """Documents the limitation: threads start with an empty context."""

    def work():
        with tracer.start_as_current_span("call"):
            pass

    with aicontrol.volume("chat-1"):
        thread = threading.Thread(target=work)
        thread.start()
        thread.join()

    assert volumes_by_span_name(exporter) == {"call": "default"}


def test_wrap_context_carries_volume_into_thread_pool(tracer, exporter):
    def work(i):
        with tracer.start_as_current_span(f"call-{i}"):
            return i

    with ThreadPoolExecutor(max_workers=4) as pool:
        with aicontrol.volume("chat-1"):
            futures = [pool.submit(aicontrol.wrap_context(work), i) for i in range(4)]
        results = [f.result() for f in futures]

    assert results == [0, 1, 2, 3]
    assert set(volumes_by_span_name(exporter).values()) == {"chat-1"}


def test_run_in_thread_carries_volume_and_returns_result(tracer, exporter):
    def work(x, y=0):
        with tracer.start_as_current_span("call"):
            return x + y

    with aicontrol.volume("chat-2"):
        future = aicontrol.run_in_thread(work, 1, y=2)

    assert future.result(timeout=5) == 3
    assert volumes_by_span_name(exporter) == {"call": "chat-2"}


def test_run_in_thread_propagates_exceptions(exporter):
    def work():
        raise ValueError("boom")

    future = aicontrol.run_in_thread(work)

    assert isinstance(future.exception(timeout=5), ValueError)


async def test_asyncio_to_thread_already_carries_volume(tracer, exporter):
    def work():
        with tracer.start_as_current_span("call"):
            pass

    async with aicontrol.volume("chat-3"):
        await asyncio.to_thread(work)

    assert volumes_by_span_name(exporter) == {"call": "chat-3"}
