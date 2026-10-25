"""FastAPI dependencies: database sessions and the trace store, held on `app.state`."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.base import TraceStore


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_store(request: Request) -> TraceStore:
    return request.app.state.trace_store
