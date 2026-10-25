# Implementation Log: Projects

Plan: project-support-plan.md

## Task 1: SDK `init(project=...)` — Completed 2026-10-09

- **Files created/modified**:
  - `sdk/src/aicontrol/_config.py`: keyword-only `init(project, endpoint, ...)`, `resolve_project`, `resolve_endpoint`, resource attributes `aicontrol.project` and `service.name`.
  - `sdk/tests/conftest.py`, `sdk/tests/test_init.py` (rewritten), `sdk/tests/test_openai_capture.py`.
  - `api/tests/spans.py` (`capture(project=...)`) and `api/tests/e2e/test_sdk_to_api.py` (one line): renamed so callers of the old signature keep working.
- **Commands to verify**:
  - `cd sdk && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
  - `cd api && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
- **Test results**: SDK 69 passed (was 53; `test_init.py` grew from 5 to 21 tests), API 112 passed, both linters clean.
- **Deviations from plan**:
  - Touched `api/tests/spans.py` and one line of the e2e test (planned for Tasks 5 and 10) so the API suite stays green after the signature change. Both are mechanical renames; the rest of those tasks is unchanged.
  - A second `init()` call is ignored before the project is resolved, so it needs no project (the plan did not specify this).
- **Open issues / follow-ups**:
  - `examples/openai_chat.py`, `examples/fastapi_app.py`, `examples/trace_demo.py`, the root README and the web landing snippet still use `app_name=` and fail with `TypeError` until Task 10 (and Task 9 for the landing snippet).
  - The dev database and running API are untouched; nothing in this task requires a migration.

## Task 2: Database, `projects` table and migration — Completed 2026-10-09

- **Files created/modified**: `api/app/models.py` (`Project`, `Volume.project_id`, `Volume.project`, composite uniqueness, `LlmCall.app_name` removed); `api/alembic/versions/2026_10_09_1200-b5d8a3c1e7f2_add_projects.py`; `api/tests/integration/test_migrations.py`; `api/tests/integration/conftest.py`.
- **Commands to verify**: `cd api && uv run pytest tests/integration/test_migrations.py -q && uv run ruff check . && uv run ruff format --check .`
- **Test results**: migration tests 7 passed (the existing "migrations match the models" check stays green). Whole API suite: 73 passed, 25 failed, 18 errors, all in code Tasks 3-6 rewrite (volumes are still created without a project).
- **Deviations from plan**: `session_factory` in the integration conftest also truncates `projects` (needed so tests start empty, since the migration creates `default`).
- **Open issues / follow-ups**: the dev database is NOT migrated and must not run the new API code before `cd api && uv run alembic upgrade head` (the running dev API uses `fastapi run` without reload, so it is unaffected until restarted).

## Task 3: Storage keys — Completed 2026-10-09

- **Files created/modified**: `api/app/storage/base.py`, `api/tests/unit/test_trace_keys.py`.
- **Commands to verify**: `cd api && uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check .`
- **Test results**: unit tests 64 passed (the key tests grew from 11 to 26 cases).
- **Deviations from plan**: the `services/calls.py` edit ("pass the project") moved to Task 4, because it reads `NewCall.project`, which Task 4 introduces.
- **Open issues / follow-ups**: callers of the old one-argument `volume_prefix` remain in the integration ingest tests and the e2e test (Tasks 5 and 10).

## Task 4: Repository — Completed 2026-10-09

- **Files created/modified**: `api/app/repository.py`, `api/app/services/calls.py`, `api/tests/integration/test_repository.py`, `api/tests/integration/test_calls_service.py`, `api/tests/integration/conftest.py`, `api/tests/spans.py`, `api/tests/unit/test_otlp.py`.
- **Commands to verify**: `cd api && uv run pytest tests/integration/test_repository.py tests/integration/test_calls_service.py tests/integration/test_migrations.py tests/unit/test_trace_keys.py tests/unit/test_otlp.py -q && uv run ruff check . && uv run ruff format --check .`
- **Test results**: repository + service + migration + key tests 66 passed; `test_otlp.py` passes. Whole suite still has failures in the ingest/read layers (mapper, routes, their integration tests) that Tasks 5-6 rewrite.
- **Deviations from plan**: the `services/calls.py` edit moved here from Task 3 (it needs `NewCall.project`); the export service's project handling (`VolumeExport.project`, `snapshot["project"]`) was done here instead of Task 6 because the service signature changed with the repository; the default test project is `tests.spans.PROJECT` ("test-project") instead of "ingest-tests", so `test_otlp.py` was updated.
- **Open issues / follow-ups**: none beyond the work scheduled in Tasks 5 and 6.

## Task 5: Ingest, reject unknown projects — Completed 2026-10-09

- **Files created/modified**: `api/app/ingest/mapper.py`, `api/app/routes/ingest.py`, `api/tests/unit/test_mapper.py`, `api/tests/integration/test_ingest.py`, `api/tests/spans.py`.
- **Commands to verify**: `cd api && uv run pytest tests/unit tests/integration/test_ingest.py -q && uv run ruff check . && uv run ruff format --check .`
- **Test results**: unit + ingest tests 85 passed. Whole API suite: 137 passed, 15 failed (all in `test_read_api.py`, rewritten in Task 6).
- **Deviations from plan**: none. (The 404 takes precedence over the 400 when a request has both kinds of refused spans; the plan did not say.)
- **Open issues / follow-ups**: `routes/read.py`, `schemas.py` and `views.py` still use the old signatures and `app_name` until Task 6.

## Task 6: Read API, nested routes and project endpoints — Completed 2026-10-09

- **Files created/modified**: `api/app/routes/read.py`, `api/app/schemas.py`, `api/app/views.py`, `api/app/main.py`, `api/app/repository.py`, `README.md`, `api/tests/integration/test_read_api.py`, `api/tests/unit/test_views.py`, `api/tests/integration/test_repository.py`.
- **Commands to verify**: `cd api && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
- **Test results**: API 178 passed, 2 deselected (e2e); SDK 69 passed; both linters clean.
- **Deviations from plan**: the README endpoint table was updated here (acceptance criterion) instead of waiting for Task 10; added `repo.get_project_summary` (not listed in Task 4) for `GET /projects/{project}` and the 201 response.
- **Open issues / follow-ups**: none for the API. The dev database and running dev API are untouched: the new API code needs `cd api && uv run alembic upgrade head` before it can run against the dev database.

## Task 7: SDK, report a missing project once — Completed 2026-10-09

- **Files created/modified**: `sdk/src/aicontrol/_project_check.py` (new), `sdk/src/aicontrol/_config.py`, `sdk/pyproject.toml`, `sdk/uv.lock`, `sdk/tests/test_project_check.py` (new).
- **Commands to verify**: `cd sdk && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
- **Test results**: SDK 85 passed (69 before; 16 new), API 178 passed, both linters clean.
- **Deviations from plan**: none. (Plan item 5, whether a 404 is retried, is answered: it is not.)
- **Open issues / follow-ups**: the real end-to-end behaviour against a live API (a missing project, then creating it in the UI) is exercised in Task 10.

## Task 8: Web client, types and routing — Completed 2026-10-09

- **Files created/modified**: see the plan's completion notes for Task 8.
- **Commands to verify**: `cd web && npx tsc -b && npm run lint && npm run build`
- **Test results**: type-check, lint and the production build are clean (no web test runner exists).
- **Deviations from plan**: none.
- **Open issues / follow-ups**: until Task 9 the UI cannot choose or create a project (only by typing `/projects/<name>/volumes/<volume>`), and the landing snippet still shows `app_name`.

## Task 9: Web UI, project picker, create modal, landing — Completed 2026-10-09

- **Files created/modified**: see the plan's completion notes for Task 9.
- **Commands to verify**: `cd web && npx tsc -b && npm run lint && npm run build`; then run the API (migrated database) and `npm run dev`, create a project from the sidebar, and run an example against it.
- **Test results**: type-check, lint and build clean. Browser run in Chrome: 25 checks passed against a throwaway stack (real SDK, real API, own Postgres).
- **Deviations from plan**: the project page (`/projects/:project`) and the `Create “X”` action for a missing project were added (the plan said "and a project page if needed"); the Carbon list-box/dropdown styles were added next to modal, form and text-input.
- **Open issues / follow-ups**: a failed `GET /api/projects` after the first load keeps the old list and does not show an error (only the first load and the landing page do).

## Task 10: Examples, docs, end-to-end — Completed 2026-10-09

- **Files created/modified**: `examples/*.py` (3), `README.md`, `web/README.md`, `sdk/README.md`, `api/tests/e2e/test_sdk_to_api.py`, `sdk/src/aicontrol/_project_check.py`, `sdk/tests/test_project_check.py`.
- **Commands to verify**: `cd sdk && uv run pytest -q`; `cd api && uv run pytest -q`; `uv run ruff check . && uv run ruff format --check .` in `sdk` and `api`; `cd web && npx tsc -b && npm run lint && npm run build`; with an e2e-capable setup (`OPENAI_API_KEY` or `AICONTROL_E2E_BASE_URL`): `cd api && uv run pytest -m e2e`.
- **Test results**: SDK 88 passed; API 178 passed (3 e2e deselected); e2e subset 2 passed against a fake OpenAI; all linters, type-check and the web build clean.
- **Deviations from plan**: a fix to the Task 7 log filter (the exporter 1.45 wording) came out of the manual end-to-end run; the SDK `README.md` also got a short usage section.
- **Open issues / follow-ups**: the tool-calling/streaming e2e test was not run (needs a real model); the dev database must be migrated by the user before the new API runs against it.
