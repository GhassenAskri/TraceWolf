"""Render the real pages with the real app (read-only SELECTs on the dev database)."""
import asyncio
import sys

import httpx2

from app.config import get_settings
from app.db import create_engine, create_session_factory
from app.main import create_app
from app.storage.memory import InMemoryTraceStore


async def main(out: str) -> None:
    engine = create_engine(get_settings().database_url)
    app = create_app(session_factory=create_session_factory(engine), trace_store=InMemoryTraceStore())
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://api") as c:
        for name, url in [
            ("home", "/"),
            ("conv", "/volumes/alice-chat-42"),
            ("fragment", "/ui/conversations?current=alice-chat-42"),
        ]:
            r = await c.get(url)
            assert r.status_code == 200, (url, r.status_code)
            open(f"{out}/{name}.html", "w").write(r.text)
            print(f"{url:45} -> {name}.html ({len(r.text)} bytes)")
    await engine.dispose()


asyncio.run(main(sys.argv[1]))
