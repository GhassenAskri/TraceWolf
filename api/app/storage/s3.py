"""TraceStore on any S3-compatible service (MinIO locally, AWS S3, GCS interoperability)."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.storage.base import TraceNotFoundError, deserialize, serialize

_NOT_FOUND = {"NoSuchKey", "404", "NotFound"}


class S3TraceStore:
    """Keeps one S3 client open between ``start()`` and ``close()`` (the app's lifetime)."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        max_concurrency: int = 16,
    ) -> None:
        self.bucket = bucket
        self._client_kwargs = {
            "endpoint_url": endpoint_url or None,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
            # Path-style addressing works with MinIO and custom endpoints.
            "config": Config(s3={"addressing_style": "path"}, retries={"mode": "standard"}),
        }
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._stack: AsyncExitStack | None = None
        self._client: Any = None

    async def start(self) -> S3TraceStore:
        self._stack = AsyncExitStack()
        session = aioboto3.Session()
        self._client = await self._stack.enter_async_context(
            session.client("s3", **self._client_kwargs)
        )
        return self

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = self._client = None

    async def __aenter__(self) -> S3TraceStore:
        return await self.start()

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist (handy for local setups and tests)."""
        try:
            await self._s3.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if _code(exc) not in _NOT_FOUND:
                raise
            await self._s3.create_bucket(Bucket=self.bucket)

    async def put(self, key: str, document: dict[str, Any]) -> int:
        data = serialize(document)
        async with self._semaphore:
            await self._s3.put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType="application/json"
            )
        return len(data)

    async def get(self, key: str) -> dict[str, Any]:
        async with self._semaphore:
            try:
                response = await self._s3.get_object(Bucket=self.bucket, Key=key)
            except ClientError as exc:
                if _code(exc) in _NOT_FOUND:
                    raise TraceNotFoundError(key) from None
                raise
            async with response["Body"] as body:
                return deserialize(await body.read())

    async def get_many(self, keys: list[str]) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*(self.get(k) for k in keys)))

    async def list_prefix(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys += [obj["Key"] for obj in page.get("Contents", [])]
        return sorted(keys)

    @property
    def _s3(self) -> Any:
        if self._client is None:
            raise RuntimeError("S3TraceStore is not started; call start() or use `async with`")
        return self._client


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))
