import asyncio
import random

import pytest

import aicontrol
from tests.conftest import volumes_by_span_name


def test_span_without_volume_goes_to_default(tracer, exporter):
    with tracer.start_as_current_span("call"):
        pass

    assert volumes_by_span_name(exporter) == {"call": "default"}


def test_span_inside_volume_block_carries_volume(tracer, exporter):
    with aicontrol.volume("alice-chat-42"):
        with tracer.start_as_current_span("call"):
            pass

    assert volumes_by_span_name(exporter) == {"call": "alice-chat-42"}


def test_nested_volumes_restore_the_outer_one(tracer, exporter):
    with aicontrol.volume("outer"):
        with tracer.start_as_current_span("before"):
            pass
        with aicontrol.volume("inner"):
            with tracer.start_as_current_span("inside"):
                pass
        with tracer.start_as_current_span("after"):
            pass
    with tracer.start_as_current_span("outside"):
        pass

    assert volumes_by_span_name(exporter) == {
        "before": "outer",
        "inside": "inner",
        "after": "outer",
        "outside": "default",
    }


def test_volume_is_restored_when_block_raises(tracer, exporter):
    with pytest.raises(RuntimeError):
        with aicontrol.volume("failing"):
            raise RuntimeError("boom")

    assert aicontrol.current_volume() == "default"


async def test_async_context_manager(tracer, exporter):
    async with aicontrol.volume("async-vol"):
        with tracer.start_as_current_span("call"):
            pass

    assert volumes_by_span_name(exporter) == {"call": "async-vol"}


async def test_concurrent_tasks_never_mix_volumes(tracer, exporter):
    async def handle(i: int):
        async with aicontrol.volume(f"vol-{i}"):
            await asyncio.sleep(random.uniform(0, 0.01))
            with tracer.start_as_current_span(f"call-{i}"):
                await asyncio.sleep(0)

    await asyncio.gather(*(handle(i) for i in range(50)))

    volumes = volumes_by_span_name(exporter)
    assert len(volumes) == 50
    assert all(volumes[f"call-{i}"] == f"vol-{i}" for i in range(50))


def test_sync_decorator(tracer, exporter):
    @aicontrol.volume("support")
    def reply():
        with tracer.start_as_current_span("call"):
            return "ok"

    assert reply() == "ok"
    assert reply.__name__ == "reply"
    assert volumes_by_span_name(exporter) == {"call": "support"}
    assert aicontrol.current_volume() == "default"


async def test_async_decorator_called_concurrently(tracer, exporter):
    @aicontrol.volume("support")
    async def reply(i: int):
        await asyncio.sleep(random.uniform(0, 0.01))
        with tracer.start_as_current_span(f"call-{i}"):
            return i

    results = await asyncio.gather(*(reply(i) for i in range(10)))

    assert results == list(range(10))
    assert set(volumes_by_span_name(exporter).values()) == {"support"}
    assert aicontrol.current_volume() == "default"


async def test_set_volume_applies_to_current_task_only(tracer, exporter):
    async def request(name: str):
        aicontrol.set_volume(name)
        await asyncio.sleep(0)
        with tracer.start_as_current_span(f"call-{name}"):
            pass

    await asyncio.gather(asyncio.create_task(request("a")), asyncio.create_task(request("b")))

    assert volumes_by_span_name(exporter) == {"call-a": "a", "call-b": "b"}
    assert aicontrol.current_volume() == "default"


@pytest.mark.parametrize("bad", ["", "   ", None, 42])
def test_invalid_volume_name_is_rejected(bad):
    with pytest.raises(ValueError):
        aicontrol.volume(bad)
    with pytest.raises(ValueError):
        aicontrol.set_volume(bad)
