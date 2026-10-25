# Feature Plan: Projects

## Overview

Add a **project** level on top of volumes, set once at SDK startup, as in this reference experience:

```python
import aicontrol
from openai import OpenAI

aicontrol.init(project="My Project")        # once at startup (or AICONTROL_PROJECT=My Project)

client = OpenAI()
client.responses.create(model="gpt-5-mini", input="What is the capital of France?")
```

Every call is traced automatically (verified: `responses.create` is already captured by the OpenAI
instrumentor and stored by the API mapper). The hierarchy becomes
**project > volume (conversation) > trace > call**. Projects are created in the UI. If the project does
not exist, the API rejects the calls and the SDK logs one clear error, without affecting the app.

## Requirements Summary

Decided with the user:

1. **Projects are created in the UI**; the SDK refers to them by name. No API keys for now.
2. **Missing project**: the API rejects the calls with a clear error; the SDK logs it once and drops them; the app is never affected.
3. **Python SDK only**; the wire contract stays language-neutral (OTLP + `aicontrol.project`) so a TypeScript SDK can follow.
4. **`app_name` is removed**; the project is the only name.
5. **No project given**: `aicontrol.init()` raises. The project comes from an argument or `AICONTROL_PROJECT`.
6. **Addresses nested under the project**; the old `/api/volumes/...` addresses are removed.
7. **Existing data** moves into a project called `default` (migration).

## Architecture Decisions

| Decision | Choice | Why |
|---|---|---|
| Project identity | Unique name, trimmed, 1-255 characters, no `/` | Matches the example's `projectName`. A `/` would break the single-segment address `/projects/{project}/...`. |
| How the SDK sends it | Resource attribute `aicontrol.project` (also copied to `service.name`) | A project is per process and the mapper already reads resource attributes. The volume stays a per-block span attribute. |
| `init` signature | Keyword-only: `init(*, project=None, endpoint=None, ...)` | Old positional code `init("http://...", "my-bot")` would silently pass the endpoint as the project. `app_name=` raises `TypeError`. |
| Endpoint | Argument, else `AICONTROL_ENDPOINT`, else `http://localhost:8000` | Zero-argument ergonomics like the example; the examples already read this variable. |
| Missing project on the API | HTTP 404 + header `X-AIControl-Error: project-not-found` when nothing in the request is accepted; HTTP 400 when spans carry no project at all; a mixed request stores the valid spans and reports the others in `partial_success` | Gives the SDK a clear signal in the normal case (one process, one project). |
| SDK reporting | A response hook on the exporter's HTTP session logs once per outage; a background check at `init()` calls `GET /api/projects/{project}` | The message appears at startup, never blocks, and calls flow again once the project is created, with no restart. |
| Storage keys | New objects: `projects/{project}/volumes/{volume}/...`; old objects stay where they are | Each row stores its own key, so old data keeps working with no S3 migration. |
| Database | New `projects` table; `volumes.project_id`; uniqueness (project, name); `llm_calls.app_name` dropped | Two projects can share a volume name. |
| Browser POST | CORS allows `POST` and the `content-type` header | The UI creates projects with a JSON POST; the API currently allows only GET. |
| UI | Project dropdown + "New project" modal at the top of the sidebar; project in the URL; last project remembered in `localStorage` | One place to switch, shareable links. |

## Implementation Tasks

Order matters: the SDK comes first because the API tests generate their spans with the SDK.

### Task 1: SDK `init(project=...)`

**Files to modify/create**:
- `sdk/src/aicontrol/_config.py` - new signature, project and endpoint resolution, resource attributes `aicontrol.project` and `service.name`
- `sdk/tests/conftest.py`, `sdk/tests/test_init.py`, `sdk/tests/test_openai_capture.py` - switch from `app_name` to `project`

**Implementation**:
1. `init(*, project=None, endpoint=None, span_exporter=None, batch=True, instrument=True)`.
2. Project from the argument, else `AICONTROL_PROJECT`; if neither, raise `ValueError("aicontrol.init() needs a project: ...")`.
3. Validate the project: non-empty, at most 255 characters, no `/`.
4. Update the docstring and the "already initialised" warning.

**Tests** (implement alongside):
- [x] Missing project raises a clear error
- [x] The environment variable works; the argument beats it
- [x] Invalid names are rejected
- [x] A positional call and `app_name=` both raise `TypeError`
- [x] The resource carries `aicontrol.project` and `service.name`

**Acceptance criteria**:
- [x] `aicontrol.init(project="X")` and `AICONTROL_PROJECT=X` plus `init()` both work
- [x] The SDK suite is green

**Completion Notes**:
- **Files modified**: `sdk/src/aicontrol/_config.py`; `sdk/tests/conftest.py`, `test_init.py` (rewritten, 21 tests), `test_openai_capture.py`; also `api/tests/spans.py` and `api/tests/e2e/test_sdk_to_api.py` (see Deviations).
- **Key decisions**:
  - `init(*, project=None, endpoint=None, span_exporter=None, batch=True, instrument=True)`: all keyword-only.
  - New public helpers in `_config.py`: `resolve_project(project)` (argument, else `AICONTROL_PROJECT`; trimmed; `ValueError` if missing, blank, not a string, over 255 characters, or containing `/`) and `resolve_endpoint(endpoint)` (argument, else `AICONTROL_ENDPOINT`, else `http://localhost:8000`; an empty value counts as unset).
  - Constants in `_config.py`: `PROJECT_ENV`, `ENDPOINT_ENV`, `PROJECT_ATTRIBUTE = "aicontrol.project"`, `MAX_PROJECT_NAME_LENGTH = 255`.
  - A second `init()` is ignored *before* the project is resolved, so it needs no project and never raises (the warning no longer echoes arguments).
  - A failed `init()` (invalid or missing project) leaves the SDK uninitialised.
  - The resource carries `aicontrol.project` and `service.name`, both set to the trimmed project.
- **Patterns established**: SDK tests use a `no_project_env` fixture to clear `AICONTROL_PROJECT` and `AICONTROL_ENDPOINT`, and an `init_and_capture(**kwargs)` helper returning the resource attributes of one span.
- **Integration points**: the API mapper (Task 5) must read `aicontrol.project` from `span.resource`. Today it still maps `service.name` to `app_name`, which keeps working only because `service.name` equals the project.
- **Notes for next task**: `api/tests/spans.py` now has `capture(*calls, project="ingest-tests")`. Task 5 should rename its remaining `app_name` assertions. The examples (`examples/*.py`) and the README still call `init(app_name=...)` and fail with `TypeError` until Task 10.

**Status**: Completed

### Task 2: Database, `projects` table and migration

**Files to modify/create**:
- `api/app/models.py` - add `Project`; add `Volume.project_id` and a relationship; uniqueness (`project_id`, `name`); drop `LlmCall.app_name`
- new migration under `api/alembic/versions/`

**Implementation**:
1. Create `projects`, insert `default`.
2. Add `volumes.project_id` nullable, backfill to `default`, then NOT NULL + foreign key.
3. Drop `volumes_name_key`, add `uq_volumes_project_name`, drop `llm_calls.app_name`.
4. Downgrade re-adds a nullable `app_name` and restores global uniqueness; it fails with a clear message if two projects share a volume name.

**Tests** (implement alongside):
- [x] The migration-versus-models check stays green
- [x] Upgrade from the previous revision with data: volumes land in `default`, calls intact
- [x] The downgrade/upgrade round trip still works

**Acceptance criteria**:
- [x] Existing calls stay visible, with project `default`

**Completion Notes**:
- **Files created/modified**: `api/app/models.py`; new `api/alembic/versions/2026_10_09_1200-b5d8a3c1e7f2_add_projects.py` (revision `b5d8a3c1e7f2`, after `7c3e91a5d2b4`); `api/tests/integration/test_migrations.py` (7 tests); `api/tests/integration/conftest.py` (`session_factory` now also truncates `projects`).
- **Key decisions**:
  - `Project(id, name unique String(255), created_at)`. `Volume.project_id` is a NOT NULL foreign key to `projects.id` (`ondelete=CASCADE`), `Volume.name` is no longer unique alone, and `uq_volumes_project_name` is unique on (`project_id`, `name`).
  - `Volume.project` is a relationship with `lazy="joined"`, like `LlmCall.volume`, so a call's project name is `call.volume.project.name` with no extra query.
  - The migration inserts the project `default` and moves every existing volume into it. It drops `llm_calls.app_name`.
  - The downgrade refuses (with a clear `RuntimeError`) while a volume name exists in several projects. It restores `volumes_name_key`, re-adds a nullable `app_name` (values are lost) and drops `projects`.
- **Patterns established**: migration tests use raw SQL on a real Postgres and a helper `empty_tables(url)` that truncates `llm_calls, volumes, projects`. Each test that changes the schema restores `head` and empties the tables in a `finally`.
- **Test utilities added**: `BEFORE_PROJECTS = "7c3e91a5d2b4"` and `empty_tables` in `test_migrations.py`.
- **Notes for next task**:
  - A fresh test database has a `default` project from the migration, but the `session_factory` fixture truncates `projects`, so tests start with none and must create the projects they need (Task 4 adds a helper).
  - `select(Volume, func.count(...)).group_by(Volume.id)` (`repo.list_volumes`) will break with the joined `project` relationship: Task 4 rewrites those queries to select columns, not the entity.
  - **The rest of the API suite is red until Tasks 3-6** (25 failed, 18 errors): the old code creates volumes without a project. Task 2's own tests are green.

**Status**: Completed

### Task 3: Storage keys

**Files to modify/create**:
- `api/app/storage/base.py` - `build_trace_key(project, volume, ...)`, `project_prefix`, `volume_prefix(project, volume)`, project name limit
- `api/app/services/calls.py` - pass the project
- `api/tests/unit/test_trace_keys.py`

**Tests** (implement alongside):
- [x] The new layout and percent-encoding, including spaces and `@`
- [x] Keys are deterministic
- [x] Two projects with the same volume name get different keys

**Acceptance criteria**:
- [x] Old rows still load through their stored key

**Completion Notes**:
- **Files modified**: `api/app/storage/base.py`; `api/tests/unit/test_trace_keys.py` (rewritten, 26 cases).
- **Key decisions**:
  - New layout `projects/{project}/volumes/{volume}/{YYYY}/{MM}/{DD}/{HHMMSS}_{trace}_{span}.json`. `project_prefix(project)` and `volume_prefix(project, volume)` are new, and `build_trace_key(project, volume, started_at, trace_id, span_id)` takes the project first.
  - Project and volume names share one encoder (`_segment`): percent-encoded into a single segment (spaces become `%20`, `/` becomes `%2F`, dot-only names become `%2E…`), so a project cannot reach into another project's prefix.
  - Added `MAX_PROJECT_NAME_LENGTH = 255`; `MAX_VOLUME_NAME_LENGTH` is unchanged (the mapper imports it).
  - Rows stored before projects keep their old `volumes/{volume}/...` key, so they still load; nothing is moved in S3.
- **Notes for next task**:
  - `api/app/services/calls.py` still calls `build_trace_key(c.row.volume, ...)`. It needs `NewCall.project`, so that edit moved to Task 4 (see Deviations).
  - `tests/integration/test_ingest.py` and `tests/e2e/test_sdk_to_api.py` still call `volume_prefix(volume)` with one argument; they are rewritten in Tasks 5 and 10.

**Status**: Completed

### Task 4: Repository

**Files to modify/create**:
- `api/app/repository.py`
- `api/tests/integration/test_repository.py` (and helpers)

**Implementation**:
1. `NewCall.project` required; `app_name` removed.
2. Add `create_project`, `get_project`, `list_projects` (counts and last activity), `existing_project_names`.
3. Add `ProjectExistsError` and `UnknownProjectError`.
4. Every volume and call function takes the project: `upsert_volume` (conflict on project and name), `insert_calls`, `list_recent_volumes`, `list_volumes`, `get_volume`, `list_calls`, `list_calls_until`.

**Tests** (implement alongside):
- [x] Create, get, and a duplicate raising
- [x] The same volume name in two projects stays separate (including pagination and the export cutoff)
- [x] An unknown project raises
- [x] Counts are per project

**Acceptance criteria**:
- [x] No query returns another project's calls

**Completion Notes**:
- **Files modified**: `api/app/repository.py` (rewritten around projects), `api/app/services/calls.py`; tests: `api/tests/integration/test_repository.py` (rewritten, 31 tests), `test_calls_service.py` (rewritten, 8 tests), `api/tests/integration/conftest.py`, `api/tests/spans.py`, `api/tests/unit/test_otlp.py`.
- **Key decisions**:
  - `NewCall.project` is the first, required field; `app_name` is gone. Calls are inserted by project *name*; `insert_calls` looks the ids up and raises `UnknownProjectError(names)` before writing anything (so a batch with one unknown project stores nothing). Volumes are created inside their project on first call.
  - New: `create_project` (raises `ProjectExistsError`; case-sensitive names), `get_project`, `list_projects` (alphabetical, case-insensitive; `ProjectSummary(name, volume_count, call_count, created_at, last_activity_at)`), `existing_project_names`.
  - Every volume/call function takes the project name first: `upsert_volume(session, project_id, name, at)`, `list_volumes(session, project)`, `list_recent_volumes(session, project, limit)`, `get_volume(session, project, name)`, `list_calls(session, project, volume, ...)`, `list_calls_until(session, project, volume, until)`. They filter with a scalar subquery on the project name (`_project_id`), so an unknown project simply returns nothing.
  - `list_volumes` and `list_projects` select columns, not the `Volume` entity, because the joined `Volume.project` relationship would break their GROUP BY.
  - `services/calls.py`: `store_calls` builds keys with `c.row.project`; `export_volume(session, store, project, volume, until)` returns a `VolumeExport` with `project`, and the snapshot has a `"project"` key (this part moved here from Task 6 because the service signature had to change).
  - Test infrastructure: `tests.spans.PROJECT = "test-project"` is the project every integration test starts with (the `session_factory` fixture truncates everything and inserts it); `capture(project=PROJECT)` uses it too.
- **Test utilities added**: `make_call(..., project=PROJECT)`; `seed_two_projects(session)` in `test_repository.py` (volume `chat` with 3 calls in `one` and 2 in `two`).
- **Notes for next task**:
  - `app/ingest/mapper.py` still builds `NewCall(...)` without `project` and still maps `service.name` to `app_name`: Task 5 reads `aicontrol.project` from `span.resource`. `test_mapper.py` still asserts `row.app_name == "ingest-tests"` and `service.name == "ingest-tests"`.
  - `routes/read.py`, `routes/ingest.py`, `schemas.py`, `views.py` still use the old signatures and `app_name`. The ingest/read integration tests are rewritten in Tasks 5-6.

**Status**: Completed

### Task 5: Ingest, reject unknown projects

**Files to modify/create**:
- `api/app/ingest/mapper.py` - read `aicontrol.project` from the resource; `project` in the trace document; remove `app_name`
- `api/app/routes/ingest.py` - check the projects; return 404, 400 or partial success as decided
- `api/tests/spans.py` - `capture(project=...)`
- unit and integration tests

**Tests** (implement alongside):
- [x] The mapper maps the project
- [x] An unknown project gives 404 + the header and stores nothing
- [x] No project attribute gives 400
- [x] A mixed request stores the valid spans and reports the rest
- [x] Non-LLM spans stay ignored

**Acceptance criteria**:
- [x] The ingest contract in the decisions table holds

**Completion Notes**:
- **Files modified**: `api/app/ingest/mapper.py`, `api/app/routes/ingest.py`; tests: `api/tests/unit/test_mapper.py`, `api/tests/integration/test_ingest.py` (rewritten; 8 new project tests), `api/tests/spans.py` (`without_project(request)`).
- **Key decisions**:
  - The mapper reads the project from the **resource** attribute `aicontrol.project` (trimmed) into `NewCall.project`; the trace document has `"project"` and no longer `"app_name"`. A missing, blank or non-string project raises `mapper.NoProjectError` (a `MappingError`).
  - The route resolves the projects with one query (`repo.existing_project_names`) and then: nothing accepted because the project is unknown → **404**; nothing accepted because spans carry no project → **400**; both with plain-text message and header `X-AIControl-Error` (`project-not-found` / `project-missing`). If at least one call is accepted, those are stored and the refused ones go in `partial_success` (status 200), with messages like `<span>: project 'Ghost' not found`. 404 takes precedence over 400 when both occur.
  - Non-LLM spans (for example the parent span `aicontrol.trace()` opens) are ignored before any project check; the ingest never creates a project.
  - Message for 404: `Project 'X' not found. Create it in the AIControl UI, then send the calls again.`
- **Test utilities added**: `s.without_project(request)` (bytes of a request with the project resource attribute removed); `calls_in(session_factory, volume, project=PROJECT)` and `create_project(session_factory, name)` in `test_ingest.py`.
- **Integration points**: Task 7's SDK hook relies on exactly this contract (404 + `X-AIControl-Error: project-not-found`). The SDK's startup check will use `GET /api/projects/{project}` from Task 6.
- **Notes for next task**: only `tests/integration/test_read_api.py` (15 tests) still fails; it needs the nested routes, `schemas.py`, `views.py` (transcript header) and CORS from Task 6. `routes/read.py` still calls the old repository signatures.

**Status**: Completed

### Task 6: Read API, nested routes and project endpoints

**Files to modify/create**:
- `api/app/routes/read.py`, `api/app/schemas.py`, `api/app/views.py`, `api/app/main.py` (CORS)
- `api/tests/integration/test_read_api.py` and `test_calls_service.py`, rewritten for the new addresses

**Implementation**:
1. Add `GET/POST /api/projects` (POST: 201, 409 duplicate, 422 invalid name) and `GET /api/projects/{project}`.
2. Move conversations, volumes, calls and export under `/api/projects/{project}/...`; remove the old routes.
3. `GET /api/calls/{id}` stays; `CallSummary` gains `project`.
4. The export and the transcript name the project.
5. CORS allows POST and the `content-type` header.

**Tests** (implement alongside):
- [x] The projects endpoints, including the error cases
- [x] Every nested route
- [x] The old routes are gone
- [x] A CORS preflight for POST succeeds

**Acceptance criteria**:
- [x] The README endpoint table matches the code

**Completion Notes**:
- **Files modified**: `api/app/routes/read.py` (rewritten), `api/app/schemas.py`, `api/app/views.py`, `api/app/main.py` (CORS), `api/app/repository.py` (`get_project_summary`), `README.md` (endpoint table); tests: `api/tests/integration/test_read_api.py` (rewritten, 44 tests), `api/tests/unit/test_views.py`, `api/tests/integration/test_repository.py`.
- **Key decisions**:
  - Routes, all under `/api`: `GET /projects`, `POST /projects` (201; 409 duplicate; 422 invalid), `GET /projects/{project}`, `GET /projects/{project}/volumes`, `GET /projects/{project}/conversations?limit=`, `GET /projects/{project}/volumes/{name:path}/calls`, `GET /projects/{project}/volumes/{name:path}/export`; `GET /calls/{id}` is unchanged. The old `/api/volumes...` and `/api/conversations` routes are gone (404).
  - Project names are validated by `schemas.ProjectName`: trimmed, 1-255 characters, no `/` (422 otherwise); `{"name": 3}` is rejected; names are case-sensitive; spaces work (`/api/projects/My%20Project`).
  - 404 messages: `Project 'X' not found` (any route under an unknown project) and `Volume 'v' not found in project 'p'`. `_require_volume` does a single query on the hot path and only looks the project up to build the clearer 404.
  - Schemas: `CallSummary` has `project` and no `app_name`; `CallPageOut` and `VolumeExportOut` carry `project`; new `ProjectOut`, `ProjectCreate`. The transcript starts `# Project: P` / `# Volume: V` / `# N calls up to ...`.
  - CORS allows `GET` and `POST` and the `content-type` header (for the UI's JSON POST); other origins stay refused.
- **Integration points**: the SDK startup check (Task 7) uses `GET /api/projects/{project}`; the web client (Task 8) uses all the routes above and `POST /api/projects`.
- **Notes for next task**: the API is complete and its whole suite is green (178 passed). The SDK's missing-project reporting (Task 7) relies on the ingest contract from Task 5.

**Status**: Completed

### Task 7: SDK, report a missing project once

**Files to modify/create**:
- new `sdk/src/aicontrol/_project_check.py`, wired into `_config.py`
- `sdk/tests/test_project_check.py`

**Implementation**:
1. Give the exporter a `requests.Session` with a response hook; on a 404 carrying `X-AIControl-Error: project-not-found`, log one ERROR naming the project and saying to create it in the UI.
2. Keep the project's state so it logs again only if the project disappears after having worked.
3. At `init()`, a daemon thread calls `GET /api/projects/{project}`; it logs the same message on 404, stays quiet if the API is unreachable, and never blocks startup.
4. Only the default exporter gets this, not injected test exporters.
5. Confirm during this task that the OTLP exporter does not retry a 404; fall back to another status if it does.

**Tests** (implement alongside):
- [x] Stub HTTP server: a 404 gives exactly one ERROR; repeated 404s add none
- [x] A later 200 resets the state
- [x] Connection refused gives no exception and no error
- [x] `init()` returns immediately

**Acceptance criteria**:
- [x] The app keeps running with the project missing, and calls flow after the project is created, with no restart

**Completion Notes**:
- **Files created/modified**: new `sdk/src/aicontrol/_project_check.py`; `sdk/src/aicontrol/_config.py` (wiring, `shutdown()`); `sdk/pyproject.toml` (+ `uv.lock`: `requests>=2.31,<3` is now a declared dependency, it was only transitive); new `sdk/tests/test_project_check.py` (16 tests, with a local stub HTTP server standing in for the API).
- **Key decisions**:
  - `ProjectMonitor(project, endpoint)` holds the state and logs `aicontrol: the project 'X' does not exist on <endpoint>. Create it in the AIControl web UI; until then its calls are dropped (the application is not affected).` **once per outage** at ERROR on logger `aicontrol`. `report_found()` (a 2xx) resets it, so the message appears again only if the project disappears after having worked; a project created later needs no restart.
  - Two sources feed it: `check()` (a `GET {endpoint}/api/projects/{percent-encoded project}`; 404 reports missing, 2xx clears it, anything else or an unreachable API says nothing, only a DEBUG line) and a response hook on the exporter's `requests.Session` (a 404 counts only with `X-AIControl-Error: project-not-found`, so a wrong endpoint is never mistaken for a missing project).
  - `init()` starts `check()` in a daemon thread, so it never waits for the API. It only does this (and uses the monitor's session) for the default OTLP exporter; an injected `span_exporter` gets no check and no filter.
  - Verified the plan's open risk: the OTLP exporter retries only 408 and 5xx, so a 404 is one attempt (confirmed by the test, three exports give three POSTs).
  - The exporter logs `Failed to export span batch code: 404` for every batch; a logging filter on `opentelemetry.exporter.otlp.proto.http.trace_exporter` drops that record only while the monitor knows the project is missing. `shutdown()` closes the monitor and removes the filter (no leak across init/shutdown cycles).
- **Test utilities added**: `Stub` HTTP server, `wait_for`, `a_span` and an `errors` fixture (ERROR records of the `aicontrol` logger) in `test_project_check.py`.
- **Integration points**: relies on the API contract from Tasks 5-6 (404 + header on ingest; `GET /api/projects/{project}`).
- **Notes for next task**: nothing in the SDK is left for the plan except documentation (Task 10). The web tasks (8-9) start from the API as documented in the README table.

**Status**: Completed

### Task 8: Web client, types and routing

**Files to modify/create**:
- `web/src/api/types.ts`, `client.ts`, `App.tsx`
- `web/src/hooks/useCurrentProject.ts` (new), `useCurrentVolume.ts`, `useCalls.ts`
- `web/src/components/ConversationList.tsx`, `TraceDetail.tsx` (the "App" field becomes "Project")

**Implementation**:
1. The client gets `projects()`, `createProject(name)`, and project-scoped `conversations` and `calls`.
2. The route becomes `projects/:project/volumes/*`.
3. Links and hooks use the project.

**Tests** (implement alongside):
- [x] No web test runner exists; checks are type-checking, the build and lint (as today)

**Acceptance criteria**:
- [x] The build and lint are clean

**Completion Notes**:
- **Files created/modified**: `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/App.tsx`, `web/src/hooks/useCurrentProject.ts` (new), `useCurrentVolume.ts`, `useCalls.ts`, `web/src/components/ConversationList.tsx`, `Sidebar.tsx`, `TraceDetail.tsx`, `web/src/pages/VolumePage.tsx`.
- **Key decisions**:
  - `client.ts` has one `request(method, path, {params, body, signal})`; `get` is a thin wrapper. New: `api.projects()`, `api.createProject(name)` (JSON POST; 409 = name taken, 422 = invalid), and project-scoped `api.conversations(project, limit)` and `api.calls(project, volume, {limit, cursor})`. Error details: a string `detail` is used as is; a FastAPI validation list (422) is joined into one message.
  - Types: `Project`, `CallSummary.project` (and `CallPage.project`), no more `app_name`.
  - Routes: `/projects/:project/volumes/*` (the splat keeps `team/support` working, encoded or not). `useCurrentProject()` reads `/projects/:project/*`, `useCurrentVolume()` reads the volume part. Project names in the URL are percent-encoded everywhere (`encodeURIComponent`).
  - `useCalls(project, volume)` restarts when either changes. `VolumePage` shows the API's own 404 text (for example `Project 'X' not found`) and sets the tab title to `volume · project · AIControl`.
  - `ConversationList` takes `project` and is remounted per project (`key`) so its "Load more" limit resets; with no project it shows "Choose a project to see its conversations." and requests nothing.
  - In the details panes the `App` field is replaced by `Project` (a call's Details, and the trace overview).
- **Notes for next task**: there is still no way to pick or create a project in the UI (the sidebar only reads the project from the URL), and `pages/Landing.tsx` still shows `app_name`: Task 9 adds the picker, the create modal, the landing page and the project page. No web test runner exists, so Task 8 is checked by type-check, build and lint; the browser check happens in Task 9.

**Status**: Completed

### Task 9: Web UI, project picker, create modal, landing

**Files to modify/create**:
- new `web/src/components/ProjectPicker.tsx`, `NewProjectModal.tsx`, `web/src/hooks/useProjects.ts`
- `Sidebar.tsx`, `pages/Landing.tsx` (and a project page if needed), `styles/app.scss` (re-add the Carbon `text-input`, `form` and `modal` styles; add `dropdown`/`list-box` for the picker)

**Implementation**:
1. The dropdown lists the projects; "New project" opens a modal with a name field.
2. The modal shows the API's errors inline (already exists, invalid name).
3. With no projects, the landing page invites you to create one; the SDK snippet shows the selected project.
4. The last project used is remembered in `localStorage`, wrapped in try/catch.

**Tests** (implement alongside):
- [x] Driven in real Chrome against a throwaway stack: create a project, a duplicate, an invalid name, switch projects, the empty state, dark mode, phone width

**Acceptance criteria**:
- [x] The scenarios above work with no console errors

**Completion Notes**:
- **Files created/modified**: new `web/src/components/ProjectsProvider.tsx`, `ProjectPicker.tsx`, `NewProjectModal.tsx`, `SdkSnippet.tsx`; new `web/src/hooks/useProjects.ts`, `web/src/lib/lastProject.ts`, `web/src/lib/projectName.ts`, `web/src/pages/ProjectPage.tsx`; modified `Layout.tsx`, `Sidebar.tsx`, `pages/Landing.tsx` (rewritten), `App.tsx`, `styles/app.scss` (re-added the Carbon `text-input` and `form` styles, plus `dropdown`, `list-box` and `modal`; new `.project-picker`, `.project-list`, `.project-name`, `.project-meta`).
- **Key decisions**:
  - `ProjectsProvider` (in `Layout`) loads `GET /api/projects` once for the whole app, exposes it through `useProjects()` (`status`, `projects`, `error`, `reload`, `openNewProject`, `createProject`) and hosts the "New project" dialog, so the sidebar and the pages share one list. The dialog is mounted only while open, so its state is thrown away on close.
  - Sidebar: a Carbon `Dropdown` (alphabetical, the API's order) plus a "New project" button above "Observe"; picking a project goes to `/projects/<name>`. The conversation list is only fetched for a project that exists (a not-yet-created project shows no red error in the sidebar).
  - `NewProjectModal` validates like the API (`lib/projectName.ts`: trimmed, 1-255 characters, no "/"), shows server errors inline (409 becomes `A project named “X” already exists.`), and the error clears as you type.
  - `/` : loading, error with Retry, no projects ("Create your first project" with the snippet), or the last project opened that still exists (`localStorage` key `aicontrol.lastProject`, every access in try/catch) redirects to its page, else "Choose a project" tiles.
  - `/projects/:project` (`ProjectPage`): name, counts, last activity and the SDK snippet with the project name filled in (`JSON.stringify` gives a valid Python string). For a project that does not exist yet it explains that calls are rejected and offers `Create “X”` (this is the page the SDK's error message points to).
  - `SdkSnippet` shows `aicontrol.init(project="…")` then `client.responses.create(...)`.
- **Verification** (no web test runner): type-check, lint and build are clean, and a Chrome run (puppeteer, throwaway stack with its own Postgres and a real SDK run) passed 25 checks: empty state; invalid and blank names refused; creating opens the page; duplicate refused; the real SDK logs one error while the project is missing and no error once it exists; the conversation and the three-step trace tree appear under the project; the dropdown lists projects alphabetically and switches; unknown project page and `Create` button; the API message for an unknown project in a conversation URL; the last project is remembered; no horizontal overflow at 390px; no console or page errors. Dark mode and the phone navigation were looked at in screenshots.
- **Notes for next task**: `examples/*.py` and the SDK/root README still use `app_name=` (Task 10). The throwaway stack used for verification (Postgres on :5544, API on :8765, vite on :5173) is left running for Task 10's end-to-end run and is stopped there.

**Status**: Completed

### Task 10: Examples, docs, end-to-end

**Files to modify/create**:
- `examples/openai_chat.py`, `examples/fastapi_app.py`, `examples/trace_demo.py`
- `README.md`, `web/README.md`, `sdk/README.md`
- `api/tests/e2e/test_sdk_to_api.py`

**Implementation**:
1. Examples use `init(project=...)`, taking it from a flag or the environment.
2. The docs get the new usage and a migration note: run `alembic upgrade head`; `app_name` is gone.
3. The end-to-end tests create the project through the API first.
4. Final run: all suites, lint, the build, and `trace_demo.py` against a project that does not exist yet (it should log the error once, then flow after the project is created).

**Tests** (implement alongside):
- [x] All suites green, lint clean, the build clean
- [x] The manual end-to-end demo behaves as described

**Acceptance criteria**:
- [x] Everything is green and the demo behaves as described

**Completion Notes**:
- **Files modified**: `examples/openai_chat.py`, `examples/trace_demo.py` (`--project`, default `$AICONTROL_PROJECT`; a friendly argparse error if neither), `examples/fastapi_app.py` (`aicontrol.init()` reads `AICONTROL_PROJECT` / `AICONTROL_ENDPOINT`); `README.md` (intro, diagram, quickstart with the "create a project" step, SDK usage, Web UI, examples, storage layout, a migration warning and a new "Upgrading to projects" section), `web/README.md`, `sdk/README.md`; `api/tests/e2e/test_sdk_to_api.py`; plus a fix in `sdk/src/aicontrol/_project_check.py` found during the manual run (below).
- **Key decisions**:
  - End-to-end tests create the project through `POST /api/projects` first (`create_project` helper, 201 or 409 accepted), use the nested addresses and assert `project`; a new test, `test_calls_for_a_missing_project_are_refused_then_flow_once_it_is_created`, drives the real SDK through the whole flow (one logged error, application unaffected, calls arrive after the project is created).
  - **Bug found by running the real example**: exporter 1.45 words its refusal as a template (`"Failed to export %s batch code: %s ..."`, kind first), so the log filter from Task 7 no longer matched and an extra `Failed to export spans batch code: 404` line was printed. The filter now matches the *formatted* message (`Failed to export spans? batch code: 404`) and a test covers the three wordings (older, newer, templated 1.45).
  - The README's migration section says to migrate before starting a newer API (otherwise the UI shows "Cannot reach the API").
- **Verification**:
  - SDK 88 passed, API 178 passed (3 e2e deselected), ruff clean on sdk, api and examples, web type-check, lint and build clean.
  - e2e against a fake OpenAI server with real Postgres and MinIO: 2 passed (`missing_project`, `fastapi_example`). The big tool-calling/streaming e2e test was only edited mechanically (addresses and project) and NOT run: it needs a real model.
  - Manual end-to-end with `examples/trace_demo.py` on a throwaway stack: with a missing project the developer sees one line (`aicontrol: the project 'Typo Project' does not exist on http://localhost:8765. Create it in the AIControl web UI; ...`), the app runs to the end and nothing is stored; after `POST /api/projects` the same script stores three calls in one trace under the project. The UI journey was verified in Chrome in Task 9.
- **Notes**: the throwaway stack (Postgres :5544, API :8765, vite :5173, fake OpenAI :8791) was torn down. The user's dev database (:5442) and dev API (:8000) were never touched: before restarting the dev API with the new code run `cd api && uv run alembic upgrade head`.

**Status**: Completed

## Risks and Mitigations

1. **Breaking changes**: `init` is keyword-only with no `app_name`, the old addresses are gone, and `app_name` data is dropped. Document them; the migration docstring says the values are not recoverable on downgrade.
2. **Migrate before running the new API**: otherwise the UI shows "Cannot reach the API" even though the API is up (this already happened once with the trace-name columns). The README says so; the dev database is migrated only when the user asks.
3. **Early calls are lost** if the project does not exist yet. This was the user's choice; the SDK logs it once.
4. **Exporter retry behaviour on a 404** is verified in Task 7, with a fallback.
5. **Names are case-sensitive**: `My Project` and `my project` would be different projects. The startup error and the dropdown make a typo visible.
6. **Test churn**: most API tests ingest spans, so they need a project to exist. A shared fixture handles it.

## Out of Scope

- A TypeScript SDK
- Renaming or deleting projects
- Per-project API keys and permissions
- Overriding the project per code block (like `aicontrol.volume(...)`)
- Moving a volume between projects
- A project settings page
- Case-insensitive names
- Making the UI tell a 500 from "unreachable"
- Pagination of the project list
