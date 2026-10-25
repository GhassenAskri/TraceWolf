"""End-to-end fixtures: the real API server (uvicorn, random port) on real Postgres + MinIO, and
the settings for the real LLM API. No mocks anywhere."""

import asyncio
import os
import socket
import threading
import time
import uuid
from pathlib import Path

import pytest
import uvicorn

from app.config import Settings
from app.main import create_app
from app.storage.s3 import S3TraceStore
from tests.integration.conftest import (  # noqa: F401 - re-exported fixtures
    MINIO_PASSWORD,
    MINIO_USER,
    minio_endpoint,
    postgres_url,
)

ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


def setting(name: str) -> str | None:
    """From the environment, else the repository's root `.env`."""
    if os.environ.get(name):
        return os.environ[name]
    if ROOT_ENV.exists():
        for line in ROOT_ENV.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name and value.strip():
                return value.strip().strip("'\"")
    return None


@pytest.fixture(scope="session")
def llm():
    """Real LLM API settings. OpenAI by default; AICONTROL_E2E_BASE_URL targets any
    OpenAI-compatible server (e.g. a local Ollama at http://localhost:11434/v1)."""
    base_url = setting("AICONTROL_E2E_BASE_URL")
    api_key = setting("OPENAI_API_KEY") or ("not-needed" if base_url else None)
    if not api_key:
        pytest.skip(f"OPENAI_API_KEY not set (environment or {ROOT_ENV})")
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": setting("AICONTROL_E2E_MODEL") or "gpt-4o-mini",
    }


@pytest.fixture(scope="session")
def api_server(llm, postgres_url, minio_endpoint):  # noqa: F811
    """The real AIControl API in a background thread. Yields (base_url, settings).

    Depends on `llm` so the test is skipped before any container starts when no key is set.
    """
    settings = Settings(
        database_url=postgres_url,
        s3_endpoint_url=minio_endpoint,
        s3_bucket=f"e2e-{uuid.uuid4().hex[:12]}",
        s3_access_key=MINIO_USER,
        s3_secret_key=MINIO_PASSWORD,
    )
    asyncio.run(_create_bucket(settings))

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings=settings), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("AIControl API did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", settings
    server.should_exit = True
    thread.join(timeout=10)


async def _create_bucket(settings: Settings) -> None:
    async with S3TraceStore(
        settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    ) as store:
        await store.ensure_bucket()
