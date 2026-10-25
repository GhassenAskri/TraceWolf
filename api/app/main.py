from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.routes import ingest, read
from app.storage.base import TraceStore
from app.storage.s3 import S3TraceStore


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    trace_store: TraceStore | None = None,
) -> FastAPI:
    """Build the API. Tests inject their own session factory / trace store; otherwise both are
    created from the settings (default: environment / root `.env`) when the app starts and
    closed when it stops."""
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            if session_factory is None:
                engine = create_engine(config.database_url)
                stack.push_async_callback(engine.dispose)
                app.state.session_factory = create_session_factory(engine)
            if trace_store is None:
                app.state.trace_store = await stack.enter_async_context(
                    S3TraceStore(
                        config.s3_bucket,
                        endpoint_url=config.s3_endpoint_url,
                        access_key=config.s3_access_key,
                        secret_key=config.s3_secret_key,
                        region=config.s3_region,
                    )
                )
            yield

    app = FastAPI(title="AIControl API", lifespan=lifespan)
    # The web UI runs on its own origin: it reads (GET) and creates projects (a JSON POST, which
    # needs the content-type header allowed). The SDK's POST /v1/traces is not made by a browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    if session_factory is not None:
        app.state.session_factory = session_factory
    if trace_store is not None:
        app.state.trace_store = trace_store

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # The API serves no HTML (the web UI lives in `web/`); the address people used to open
    # leads to the interactive API documentation.
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    app.include_router(ingest.router)
    app.include_router(read.router)
    return app


app = create_app()
