from typing import Any

from app.storage.base import TraceNotFoundError, deserialize, serialize


class InMemoryTraceStore:
    """TraceStore kept in a dict, for tests. Stores serialized bytes like the real store."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, document: dict[str, Any]) -> int:
        data = serialize(document)
        self.objects[key] = data
        return len(data)

    async def get(self, key: str) -> dict[str, Any]:
        try:
            return deserialize(self.objects[key])
        except KeyError:
            raise TraceNotFoundError(key) from None

    async def get_many(self, keys: list[str]) -> list[dict[str, Any]]:
        return [await self.get(k) for k in keys]

    async def list_prefix(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))
