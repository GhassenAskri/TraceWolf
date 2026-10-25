# Implementation Log: LLM Telemetry SDK + Local API

Plan: llm-telemetry-sdk-plan.md

## Task 1: Scaffold + infrastructure + Ollama compatibility spike — Completed 2026-09-24

- **Files created/modified**: `.gitignore`, `.env.example`, `docker-compose.yml`, `README.md`, `sdk/pyproject.toml`, `sdk/.python-version`, `sdk/README.md`, `sdk/src/aicontrol/__init__.py`, `sdk/tests/test_ollama_compat_spike.py`, `api/pyproject.toml`, `api/.python-version`, `api/app/__init__.py`, `api/app/main.py`, `api/tests/__init__.py`, `api/tests/unit/test_health.py`
- **Commands to verify**:
  - `cd sdk && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .`
  - `cd api && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .`
  - `docker-compose up -d --wait && docker-compose ps -a && docker-compose logs minio-init`
- **Test results**: sdk 1 passed; api 1 passed; ruff clean in both. Compose: postgres healthy, minio healthy, minio-init exited 0 ("Bucket created successfully `local/aicontrol-traces`").
- **Resolved versions**: ollama 0.6.2, opentelemetry-instrumentation-ollama 0.62.3, opentelemetry-sdk 1.44.0, opentelemetry-exporter-otlp-proto-http 1.44.0, opentelemetry-semantic-conventions-ai 0.5.1, fastapi 0.141.1.
- **Deviations from plan**:
  - Latest `ollama` works with the instrumentor → no downgrade (plan anticipated a possible pin to 0.4.x).
  - MinIO images come from `quay.io` (removed from Docker Hub), not Docker Hub.
  - Default ports 5442 / 9100 / 9101 instead of 5432 / 9000 / 9001 (conflict with an existing local MinIO container).
  - Added `GET /health` + test in the API so `uv run pytest` has something to run.
- **Open issues / follow-ups**:
  - Local `docker compose` plugin is a broken stub (`~/.docker/cli-plugins/docker-compose`, 9 bytes); standalone `docker-compose` works. README documents both.
  - Starlette warns that `httpx` with `TestClient` is deprecated in favour of `httpx2`; revisit when adding API tests in Task 4+.
  - The compose stack was left running (`docker-compose down` to stop).

## Task 2: SDK core — init, volume context, span processor — Completed 2026-09-24

- **Files created/modified**: `sdk/src/aicontrol/__init__.py`, `sdk/src/aicontrol/_config.py`, `sdk/src/aicontrol/_volume.py`, `sdk/src/aicontrol/_processor.py`, `sdk/src/aicontrol/_context.py`, `sdk/tests/__init__.py`, `sdk/tests/conftest.py`, `sdk/tests/test_init.py`, `sdk/tests/test_volume.py`, `sdk/tests/test_context.py`
- **Commands to verify**: `cd sdk && uv run pytest -q && uv run ruff check . && uv run ruff format --check .` (pytest repeated 5× to check the concurrency tests are stable)
- **Test results**: 24 passed, 0 failed (5/5 runs); ruff clean.
- **Deviations from plan**:
  - Added `current_volume()` and `reset_volume(token)` to the public API; `set_volume()` returns a token.
  - `run_in_thread` returns a `Future` (plan didn't specify the return type).
  - Extra tests beyond the plan: volume restored after an exception, invalid names rejected, SDK doesn't replace the global tracer provider, `asyncio.to_thread` propagates the volume, OTLP URL building.
- **Open issues / follow-ups**: none.

## Plan revision — 2026-09-24

- Provider switched from Ollama to **OpenAI Chat Completions**: OpenLLMetry's Ollama instrumentor drops tool calls from replies (checked in source: `set_response_attributes` and the stream accumulator keep only content/role). OpenAI and Anthropic instrumentors capture them.
- Cost computation deferred to a separate feature; monitoring columns added to the data model instead.
- E2E tests use the real OpenAI API, no mocks; unit tests stay mocked.
- Incident: an early throwaway spike used `respx`, which does not intercept `openai` 3.x, so one request with a fake key (`sk-test`) and the prompt "Weather in Paris?" reached api.openai.com and got a 401. No real credentials or data involved. All tests now inject a mock transport.

## Task 3: SDK OpenAI capture (Chat Completions) — Completed 2026-09-24

- **Files created/modified**: `sdk/pyproject.toml`, `sdk/src/aicontrol/_instrument.py`, `sdk/src/aicontrol/_config.py`, `sdk/tests/fixtures/__init__.py`, `sdk/tests/fixtures/openai_responses.py`, `sdk/tests/test_openai_capture.py`, `sdk/tests/test_openai_live.py`, `README.md`, `.env.example`; deleted `sdk/tests/test_ollama_compat_spike.py`
- **Commands to verify**: `cd sdk && uv run pytest -q` (3×), `uv run pytest -q -m e2e -rs`, `uv run ruff check . && uv run ruff format --check .`
- **Test results**: 34 passed, 1 deselected (live); stable over 3 runs. `-m e2e`: 1 skipped ("OPENAI_API_KEY not set"). Ruff clean.
- **Resolved versions**: openai 3.19.2 (uses httpx2 2.13.1), opentelemetry-instrumentation-openai 0.62.3, opentelemetry-instrumentation 0.65b0, wrapt 2.4.1.
- **Deviations from plan**:
  - Instrument-once + delegating tracer provider instead of instrument/uninstrument per `init()`/`shutdown()` (upstream unwrap bug, see plan notes).
  - Mock transport is `httpx2`, not `httpx`/`respx`.
  - Extra tests: repeated init/shutdown cycles capture exactly once; no span after shutdown; missing `openai` package logs and skips.
- **Open issues / follow-ups**:
  - Run `uv run pytest -m e2e` once `OPENAI_API_KEY` is in the root `.env`.
  - Consider reporting the unwrap bug upstream (traceloop/openllmetry).
  - Confirm `gpt-4o-mini` is still offered on the account; otherwise set `AICONTROL_E2E_MODEL`.

## Task 4: API index database (Postgres + Alembic) — Completed 2026-09-24

- **Files created/modified**: `api/pyproject.toml`, `api/app/config.py`, `api/app/db.py`, `api/app/models.py`, `api/app/repository.py`, `api/alembic.ini`, `api/alembic/env.py`, `api/alembic/versions/2026_09_24_1530-4ec62d3af38f_create_volumes_and_llm_calls.py`, `api/tests/conftest.py`, `api/tests/integration/conftest.py`, `api/tests/integration/test_migrations.py`, `api/tests/integration/test_repository.py`, `README.md`
- **Commands to verify**: `cd api && uv run pytest -q` (2×), `uv run ruff check . && uv run ruff format --check .`, `uv run alembic upgrade head && uv run alembic current`
- **Test results**: 16 passed (3 migration, 12 repository, 1 health), ~4 s incl. Postgres container; ruff clean. Local compose DB migrated to `4ec62d3af38f (head)`.
- **Resolved versions**: sqlalchemy 2.0.54, psycopg 3.3.6, alembic 1.20.0, pydantic-settings 2.15.0, testcontainers 4.15.0.
- **Deviations from plan**:
  - Extra tests: all monitoring columns round-trip; migrations match models (`compare_metadata` empty); downgrade/upgrade round trip; calls scoped per volume; cursor returns later-arriving calls; empty page keeps cursor; invalid cursor rejected; `get_call`.
  - `httpx` → `httpx2` in API dev deps (Starlette deprecation warning); `testcontainers.community.postgres` import (old path deprecated).
- **Open issues / follow-ups**: One test-data bug fixed during the task (duplicate span IDs in the pagination test were correctly ignored by the unique constraint).

## Task 5: Trace object storage (S3 / MinIO) — Completed 2026-09-24

- **Files created/modified**: `api/pyproject.toml`, `api/app/storage/__init__.py`, `api/app/storage/base.py`, `api/app/storage/memory.py`, `api/app/storage/s3.py`, `api/app/services/__init__.py`, `api/app/services/calls.py`, `api/tests/unit/test_trace_keys.py`, `api/tests/integration/conftest.py`, `api/tests/integration/test_s3_store.py`, `api/tests/integration/test_calls_service.py`, `README.md`
- **Commands to verify**: `cd api && uv run pytest -q` (2×), `uv run ruff check . && uv run ruff format --check .`
- **Test results**: 44 passed (~8 s incl. Postgres + MinIO containers); ruff clean.
- **Resolved versions**: aioboto3 15.5.0, aiobotocore 2.25.1, botocore 1.40.61.
- **Deviations from plan**:
  - Volume names are percent-encoded in keys rather than rejected (plan said "reject `/` and `..`"); plan text updated.
  - Generic MinIO container with the pinned quay.io image instead of the testcontainers MinIO module.
  - Extra tests: list pagination past 1000 keys, `get_many` ordering, missing key → `TraceNotFoundError`, idempotent `ensure_bucket`, store used before `start()`, retried batch stored once, export of an unknown volume.
- **Open issues / follow-ups**: First encoding version escaped every dot (`example.com` → `example%2Ecom`); a test caught it and the rule was narrowed to dot-only names.

## Task 6: OTLP ingest endpoint — Completed 2026-09-24

- **Files created/modified**: `api/pyproject.toml`, `api/app/ingest/__init__.py`, `api/app/ingest/otlp.py`, `api/app/ingest/mapper.py`, `api/app/views.py`, `api/app/deps.py`, `api/app/routes/__init__.py`, `api/app/routes/ingest.py`, `api/app/main.py`, `api/alembic/env.py`, `api/tests/spans.py`, `api/tests/unit/test_otlp.py`, `api/tests/unit/test_mapper.py`, `api/tests/unit/test_views.py`, `api/tests/integration/test_ingest.py`, `api/tests/integration/conftest.py`
- **Commands to verify**: `cd api && uv run pytest -q` (2×), `uv run ruff check . && uv run ruff format --check .`; smoke: `uv run fastapi run app/main.py --port 8077` + SDK with real OTLP exporter, then `psql … select … from llm_calls` and `mc ls -r …/volumes/smoke-test/`
- **Test results**: 85 passed (49 unit, 36 integration), ~10 s; ruff clean. Smoke: `POST /v1/traces` 200, 2 rows with monitoring columns, 2 objects (2.1 KiB, 2.6 KiB).
- **Resolved versions**: opentelemetry-proto 1.44.0, protobuf 7.36.2.
- **Deviations from plan**:
  - `new_messages()` + tests done here instead of Task 7 (ingest needs the preview).
  - Malformed spans reported via OTLP `partial_success` (plan only said "logged and skipped").
  - Bad bodies → 400 (not in plan); `app/deps.py` and `create_app()` factory added for dependency injection.
  - Test spans are genuine (SDK + instrumentor + mock transport, real OTLP encoder) rather than hand-built fixtures.
- **Open issues / follow-ups**:
  - Fixed: Alembic `fileConfig` disabled existing loggers (would hide app warnings when migrating in-process).
  - Local dev DB/bucket now contain a `smoke-test` volume (2 calls) from the manual check.

## Task 7: REST read API + export — Completed 2026-09-24

- **Files created/modified**: `api/app/schemas.py`, `api/app/routes/read.py`, `api/app/views.py`, `api/app/main.py`, `api/tests/integration/test_read_api.py`, `api/tests/unit/test_views.py`
- **Commands to verify**: `cd api && uv run pytest -q`, `uv run ruff check . && uv run ruff format --check .`; smoke: `uv run fastapi run app/main.py --port 8077` then `curl` on `/api/volumes`, `/api/volumes/smoke-test/calls`, `/api/calls/{id}`, `/api/volumes/smoke-test/export?format=text`
- **Test results**: 106 passed (~11 s); ruff clean; smoke OK against Postgres + MinIO.
- **Deviations from plan**:
  - Missing trace object on the call detail returns `trace: null` + `trace_error` (200) rather than an error; export returns 502.
  - Volume names with `/` supported via `{name:path}` routes; naive datetimes interpreted as UTC.
  - `new_messages` tests were already done in Task 6.
- **Open issues / follow-ups**: a first run failed because my synthetic test rows had no `preview` (the mapper builds it in real use); fixed in the test helper, no production change.

## Task 8: Web UI (Jinja + HTMX) — Completed 2026-09-24

- **Files created/modified**: `api/app/ui/__init__.py`, `api/app/ui/routes.py`, `api/app/ui/templates/base.html`, `api/app/ui/templates/volumes.html`, `api/app/ui/templates/volume_timeline.html`, `api/app/ui/templates/partials/calls.html`, `api/app/ui/templates/partials/call_full.html`, `api/app/ui/static/app.css`, `api/app/main.py`, `api/tests/integration/test_ui.py`
- **Commands to verify**: `cd api && uv run pytest -q`, `uv run ruff check .`; visual: `uv run fastapi run app/main.py --port 8077`, seed via SDK, `Google Chrome --headless=new --screenshot=… http://localhost:8077/volumes/demo-conversation`
- **Test results**: 119 passed (~12 s); ruff clean; screenshots reviewed.
- **Deviations from plan**:
  - Time filter is a plain GET form rather than `hx-get` on change (simpler, works without JS).
  - Added "Load more" for volumes with more than 50 calls (plan only had auto-refresh); fragments under `/ui/…`.
  - htmx pinned with Subresource Integrity.
- **Open issues / follow-ups**:
  - Test-data slip: `store_messages()` reused span ids across calls (dedup correctly ignored them); fixed with a global counter.
  - Local dev data added: volume `demo-conversation` (4 calls).

## Task 9: End-to-end verification, examples, docs — Completed 2026-09-24 (real-API runs pending key)

- **Files created/modified**: `examples/openai_chat.py`, `examples/fastapi_app.py`, `api/tests/e2e/__init__.py`, `api/tests/e2e/conftest.py`, `api/tests/e2e/test_sdk_to_api.py`, `api/app/main.py`, `api/pyproject.toml`, `README.md`, `.env.example`
- **Commands to verify**:
  - `cd sdk && uv run pytest -q && uv run pytest -q -m e2e -rs`
  - `cd api && uv run pytest -q && uv run pytest -q -m e2e -rs`
  - `uv run ruff check . ../examples && uv run ruff format --check . ../examples` (from `api/`)
  - `uv run examples/openai_chat.py --help`; `uv run examples/fastapi_app.py` → `GET :8090/docs` 200
  - Harness dry run: `AICONTROL_E2E_BASE_URL=http://127.0.0.1:8199/v1 AICONTROL_E2E_MODEL=stub-model uv run pytest -m e2e` with a scratchpad stub server
- **Test results**: SDK 34 passed + 1 e2e skipped (no key); API 119 passed + 2 e2e skipped (no key, ~1 s); harness dry run 2/2 passed; ruff clean.
- **Deviations from plan**:
  - Ollama variant is the same e2e tests with `AICONTROL_E2E_BASE_URL` instead of a separate `ollama`-marked test.
  - Examples are uv inline scripts (self-installing) instead of relying on a project environment.
  - `create_app()` gained a `settings` parameter for the e2e server.
- **Open issues / follow-ups**:
  - **Run the real e2e tests** once `OPENAI_API_KEY` is in the root `.env` (SDK: 1 test, API: 2 tests).
  - Optional: run them against a local Ollama (`AICONTROL_E2E_BASE_URL=http://localhost:11434/v1`).
  - Consider reporting the OpenLLMetry `uninstrument()` bug upstream (Task 3).
  - Local dev data: volumes `smoke-test` and `demo-conversation` in the compose Postgres/MinIO; `docker-compose down -v` resets everything.
