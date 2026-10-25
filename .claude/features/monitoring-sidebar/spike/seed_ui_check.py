"""Seed 40 conversations into the THROWAWAY database (never the dev one)."""
import asyncio
from datetime import UTC, datetime, timedelta

from app import repository as repo
from app.db import create_engine, create_session_factory
from app.repository import NewCall

URL = "postgresql+psycopg://aicontrol:aicontrol@localhost:5543/aicontrol"
T0 = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)
LONG = "customer-support-escalation-thread-for-the-enterprise-onboarding-project-2026"


def call(volume: str, i: int, at: datetime) -> NewCall:
    text = f"Hello from {volume}"
    return NewCall(
        volume=volume, trace_id=f"{i:032x}", span_id=f"{i:016x}", started_at=at,
        ended_at=at + timedelta(milliseconds=500), trace_key=f"volumes/seed/{i}.json",
        request_model="gpt-4o-mini", response_model="gpt-4o-mini-2024-07-18",
        input_tokens=20, output_tokens=5, latency_ms=500, status="ok", finish_reasons=["stop"],
        preview=[{"role": "user", "content": text},
                 {"role": "assistant", "content": f"Reply to: {text}", "finish_reason": "stop"}],
    )


async def main() -> None:
    names = [f"chat-{i:02d}" for i in range(38)] + [LONG, "team/support"]  # 40; last = newest
    engine = create_engine(URL)
    async with create_session_factory(engine)() as session:
        await repo.insert_calls(session, [call(n, i + 1, T0 + timedelta(minutes=i)) for i, n in enumerate(names)])
        await session.commit()
    await engine.dispose()
    print(f"seeded {len(names)} conversations")


asyncio.run(main())
