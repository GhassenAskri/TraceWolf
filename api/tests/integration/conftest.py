"""Real Postgres (migrations applied) and real MinIO, started once per session (testcontainers)."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from app.db import create_engine, create_session_factory
from app.storage.s3 import S3TraceStore
from tests.spans import PROJECT

API_DIR = Path(__file__).resolve().parents[2]

# Same pinned image as docker-compose.yml (MinIO is no longer published on Docker Hub).
MINIO_IMAGE = "quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z"
MINIO_USER, MINIO_PASSWORD = "aicontrol", "aicontrol-secret"


def alembic_config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        url = pg.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture
async def session_factory(postgres_url):
    """Session factory on an emptied database that holds one project, ``tests.spans.PROJECT``."""
    engine = create_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE llm_calls, volumes, projects RESTART IDENTITY CASCADE"))
        await conn.execute(
            text("INSERT INTO projects (name, slug) VALUES (:name, :name)"), {"name": PROJECT}
        )
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture(scope="session")
def minio_endpoint():
    container = (
        DockerContainer(MINIO_IMAGE)
        .with_command("server /data")
        .with_env("MINIO_ROOT_USER", MINIO_USER)
        .with_env("MINIO_ROOT_PASSWORD", MINIO_PASSWORD)
        .with_exposed_ports(9000)
        .waiting_for(HttpWaitStrategy(9000, "/minio/health/live"))
    )
    with container:
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"


@pytest.fixture
async def s3_store(minio_endpoint):
    """A started S3TraceStore on a fresh bucket, so tests never see each other's objects."""
    store = S3TraceStore(
        f"test-{uuid.uuid4().hex[:12]}",
        endpoint_url=minio_endpoint,
        access_key=MINIO_USER,
        secret_key=MINIO_PASSWORD,
    )
    async with store:
        await store.ensure_bucket()
        yield store
