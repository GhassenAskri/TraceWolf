import pytest

from app.storage.base import TraceNotFoundError
from app.storage.s3 import S3TraceStore

DOC = {"volume": "alice-chat-42", "output_messages": [{"role": "assistant", "content": "22°C"}]}


async def test_put_get_round_trip_returns_size(s3_store):
    size = await s3_store.put("volumes/alice-chat-42/2026/09/24/a.json", DOC)

    assert size > 0
    assert await s3_store.get("volumes/alice-chat-42/2026/09/24/a.json") == DOC


async def test_list_prefix_returns_only_that_volume(s3_store):
    await s3_store.put("volumes/alice-chat-42/2026/09/24/a.json", DOC)
    await s3_store.put("volumes/alice-chat-42/2026/09/25/b.json", DOC)
    await s3_store.put("volumes/alice-chat-420/2026/09/24/c.json", DOC)
    await s3_store.put("volumes/support/2026/09/24/d.json", DOC)

    keys = await s3_store.list_prefix("volumes/alice-chat-42/")

    assert keys == [
        "volumes/alice-chat-42/2026/09/24/a.json",
        "volumes/alice-chat-42/2026/09/25/b.json",
    ]


async def test_put_same_key_overwrites(s3_store):
    await s3_store.put("volumes/v/k.json", {"version": 1})
    await s3_store.put("volumes/v/k.json", {"version": 2})

    assert await s3_store.get("volumes/v/k.json") == {"version": 2}
    assert await s3_store.list_prefix("volumes/v/") == ["volumes/v/k.json"]


async def test_get_missing_key_raises_trace_not_found(s3_store):
    with pytest.raises(TraceNotFoundError):
        await s3_store.get("volumes/v/missing.json")


async def test_get_many_keeps_order(s3_store):
    keys = [f"volumes/v/{i}.json" for i in range(20)]
    for i, key in enumerate(keys):
        await s3_store.put(key, {"i": i})

    docs = await s3_store.get_many(list(reversed(keys)))

    assert [d["i"] for d in docs] == list(reversed(range(20)))


async def test_list_prefix_paginates_beyond_one_page(s3_store):
    # S3 returns at most 1000 keys per page.
    import asyncio

    await asyncio.gather(*(s3_store.put(f"volumes/big/{i:05d}.json", {}) for i in range(1005)))

    assert len(await s3_store.list_prefix("volumes/big/")) == 1005


async def test_ensure_bucket_is_idempotent(s3_store):
    await s3_store.ensure_bucket()


async def test_using_store_before_start_fails_clearly():
    store = S3TraceStore("bucket")

    with pytest.raises(RuntimeError, match="not started"):
        await store.get("k")
