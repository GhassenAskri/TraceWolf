# Feature Plan: AIControl – LLM Telemetry SDK + Local API

> **Revision 2026-09-24 (during Task 3)**: provider switched from Ollama to **OpenAI Chat Completions**.
> Reason: OpenLLMetry's Ollama instrumentor drops tool calls from model replies; the OpenAI instrumentor
> captures them (verified with `openai` 3.19.2) and records richer monitoring attributes. Cost tracking is
> deferred to a separate feature. Tasks 1–2 are unaffected; Tasks 3, 6, 7, 8, 9 were updated.
> End-to-end tests use the **real OpenAI API, no mocks** (`OPENAI_API_KEY` from env or the git-ignored root `.env`, provided by the user); unit tests stay mocked.

## Overview

- **Python SDK** (`aicontrol`): plugged into code that calls the OpenAI API (Chat Completions). Captures every LLM call with OpenTelemetry (via OpenLLMetry) and sends it over OTLP/HTTP.
- **Standalone FastAPI application** (`api/`): receives the calls, stores each call's **full trace in S3-compatible object storage** and a **light index in Postgres**, grouped by **volume**. Shows them in a web UI (Jinja + HTMX) and a REST API.
- Designed for the next step: **volume-level evaluation** — give a volume + an evaluation mechanism (LLM or human judge), get back a set of scores.

## Requirements Summary

- **SDK**: Python, **OpenAI Chat Completions** only for v1 (`openai` 3.x client, including OpenAI-compatible servers via `base_url`, e.g. a local Ollama at `http://localhost:11434/v1`). Uses OpenLLMetry `OpenAIInstrumentor`, so the app's LLM code is unchanged. Other providers and fixing their tool-call gaps come later.
- **Monitoring attributes**: promote the most important attributes to Postgres columns (see data model); keep **every** attribute in the S3 trace object. **No cost computation in v1** (tokens incl. cached/reasoning are stored so cost can be added later).
- **Volume**: the storage unit holding call traces (messages, metadata, timestamps, tool calls). Calls go to volume `default` unless the code wraps them in `aicontrol.volume("name")`. The backend never guesses grouping.
- **Transport**: OTLP/HTTP, `POST /v1/traces`, batched in the background (~1s). The SDK must never break the host app.
- **Storage** (data volume will grow):
  - **Heavy data** (full input/output messages, tool calls, raw attributes) → one JSON object per call in **S3-compatible storage**, laid out by volume. Local: **MinIO** (Docker Compose). Later: AWS S3 / GCS (S3 interoperability) via config only.
  - **Light index** (volume, timestamps, model, tokens, status, S3 key, new-message preview) → **Postgres**, schema managed with Alembic.
- **Read side**: REST API + Jinja/HTMX UI; filter by volume and time range; an export endpoint returning a whole volume (the future input for evaluation).
- **Security**: none for now, local only. A nullable `user_id` column is reserved for later authentication.

## The flow (one message, end to end)

1. **Setup (once)**: `aicontrol.init(endpoint="http://localhost:8000", app_name="my-bot")` hooks the `openai` client and prepares a background exporter.
2. **Pick a volume**: `with aicontrol.volume("alice-chat-42"):` sets a contextvar for this block only; concurrent requests keep their own.
3. **App calls OpenAI unchanged**: `client.chat.completions.create(model=..., messages=history, tools=...)`.
4. **SDK records the call**: the instrumentor opens a span; `VolumeSpanProcessor` stamps `aicontrol.volume` on it at start.
5. **OpenAI answers**: the span is completed with input/output messages (incl. tool calls), request settings, response model/id, finish reason, tokens (incl. cached/reasoning), timings. The app gets its reply normally.
6. **Background send**: spans are batched and sent to `POST /v1/traces`. If the API is down, a warning is logged and the app continues.
7. **API ingests**: decodes OTLP, keeps only LLM spans, reads the volume (fallback `default`), rebuilds the message list.
8. **API stores**:
   1. writes the full trace JSON to `s3://aicontrol-traces/volumes/alice-chat-42/2026/09/24/<ts>_<trace_id>_<span_id>.json`;
   2. then writes the light index row in Postgres (with the S3 key and a new-messages preview).
9. **You view it**: UI at `http://localhost:8000` — the timeline reads only Postgres; "show full input" fetches the object from S3. REST: `GET /api/volumes/{name}/calls`.

```
app code ──(volume + openai call)──▶ SDK span ──(OTLP/HTTP batch)──▶ API ──┬──▶ S3 / MinIO  (full trace JSON)
                                                                           └──▶ Postgres      (index + preview)
                                                                                    │
                                                                    UI / REST / export (fetch from S3 on demand)
```

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Repo | `sdk/` (installable library) + `api/` (FastAPI application, run not installed) | The backend is an API, not a package |
| Capture | OpenLLMetry `opentelemetry-instrumentation-openai` (0.62.x) on the SDK's own tracer provider | Wraps sync/async/streaming `chat.completions.create`; records tool calls in replies; verified with `openai` 3.19.2 |
| Message format | New GenAI semconv: `gen_ai.input.messages` / `gen_ai.output.messages` (JSON, typed `parts`: `text`, `tool_call`, `tool_call_response`) | What the instrumentor emits; the API normalises it to `{role, content, tool_calls, tool_call_id, finish_reason}` |
| Monitoring attributes | Promoted to Postgres columns (see data model); all raw attributes kept in S3 | Fast filters/timeline on what matters; nothing lost |
| Cost | Not computed in v1 | Deferred to a dedicated feature; token counts (incl. cached/reasoning) are stored to enable it |
| Volume propagation | `contextvar` + custom `VolumeSpanProcessor.on_start` stamping `aicontrol.volume` | Safe under asyncio and concurrent requests; independent of the instrumentor |
| Transport | OTLP http/protobuf (JSON + gzip also accepted) | Standard exporter with built-in batching and retry; JSON for curl debugging |
| Heavy data storage | One JSON object per call in S3-compatible storage (Option A) | Unbounded growth kept out of the DB; each call visible immediately; volume = S3 prefix |
| Object key layout | `volumes/{volume}/{YYYY}/{MM}/{DD}/{HHMMSS}_{trace_id}_{span_id}.json` | Deterministic (retries overwrite the same object = idempotent); listing a volume or a day is a prefix scan; ready for later Parquet compaction |
| S3 client | `aioboto3` behind a `TraceStore` interface (`put`, `get`, `list_prefix`); config: `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | Plain S3 API only → MinIO ↔ AWS S3 ↔ GCS (HMAC interoperability) is a config change |
| Local S3 | MinIO, **pinned image tag** | MinIO community edition is in maintenance mode (no new community images); used only as a local stand-in |
| Index storage | Postgres 16; async SQLAlchemy 2 (psycopg 3); Alembic | Relations for future evaluation (volumes → runs → scores); small, fast queries for UI/filters |
| Write order | S3 `put` first, then Postgres insert | A crash can only leave an orphan object (harmless, re-ingest overwrites it); never an index row pointing to nothing |
| "New part" of a call | Input messages after the last `assistant` message + output; stored as `preview` JSONB in Postgres | Timeline renders from Postgres alone, without hitting S3 |
| Evaluation prep | `volumes` table + export endpoint returning ordered calls (full traces fetched from S3) and a snapshot (call IDs + cutoff) | Future evaluation runs can record exactly what they evaluated |
| UI | Jinja + HTMX served by the API, in a dedicated `app/ui/` module | Auto-refresh, expand, filter with no JS build; REST API allows a React UI later |
| Failure mode | SDK logs and never raises into the host app; API returns 5xx on S3/DB failure so the OTLP exporter retries | Telemetry must never break the app; no silent data loss on the API side |
| Idempotency | Deterministic S3 key + unique `(trace_id, span_id)` with `ON CONFLICT DO NOTHING` | Exporter retries are safe |
| Tests | **E2E: real OpenAI API, no mocks** (`OPENAI_API_KEY`, pytest marker `e2e`, skipped with an explicit reason when the key is absent); unit tests: pytest; OpenAI mocked with an `httpx.MockTransport` injected into the client (no network — `respx` does not intercept `openai` 3.x); `testcontainers` Postgres + MinIO for API tests; in-memory `TraceStore` fake for unit tests | Integration tests run against real Postgres and a real S3 API |

### Data model (Postgres = index only)

```
volumes(
  id, name UNIQUE, created_at, last_activity_at, metadata JSONB
)
llm_calls(
  id, volume_id FK -> volumes, trace_id, span_id, app_name,
  -- model / provider
  operation,                -- gen_ai.operation.name (chat)
  provider,                 -- gen_ai.provider.name (openai)
  request_model,            -- gen_ai.request.model (gpt-4o-mini)
  response_model,           -- gen_ai.response.model (gpt-4o-mini-2024-07-18)
  api_base,                 -- gen_ai.openai.api_base (OpenAI or compatible server)
  response_id,              -- gen_ai.response.id
  -- timing
  started_at, ended_at, latency_ms, is_streaming,
  -- tokens
  input_tokens, output_tokens, total_tokens,
  cached_input_tokens,      -- gen_ai.usage.cache_read.input_tokens
  reasoning_tokens,         -- gen_ai.usage.reasoning_tokens
  -- outcome
  status,                   -- ok | error (span status)
  error_type,               -- error.type
  finish_reasons TEXT[],    -- gen_ai.response.finish_reasons
  -- request settings
  temperature, max_tokens, top_p,
  -- tools
  tools_offered INTEGER,    -- count of gen_ai.tool.definitions
  tool_calls_made TEXT[],   -- names of tools requested in the reply
  preview JSONB,            -- new messages only (small), for the timeline
  trace_key TEXT,           -- S3 object key of the full trace
  trace_size_bytes INTEGER,
  user_id NULL
)
UNIQUE (trace_id, span_id)
INDEX  (volume_id, started_at)
```

### S3 object (full trace, one per call)

```json
{
  "schema_version": 1,
  "volume": "alice-chat-42",
  "trace_id": "...", "span_id": "...", "app_name": "my-bot",
  "started_at": "...", "ended_at": "...",
  "operation": "chat", "provider": "openai", "streaming": false,
  "request_model": "gpt-4o-mini", "response_model": "gpt-4o-mini-2024-07-18",
  "tokens": {"input": 45, "output": 8, "total": 53, "cached_input": 10, "reasoning": 0},
  "finish_reasons": ["tool_call"],
  "input_messages":  [{"role": "user", "content": "Weather in Paris?"}],
  "output_messages": [{"role": "assistant", "content": null,
                       "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}}],
                       "finish_reason": "tool_call"}],
  "tool_definitions": [ ... ],
  "raw_attributes": { ... },
  "resource": { "service.name": "my-bot", ... }
}
```

Next plan (not v1): `evaluation_runs(volume_id, mechanism, rubric, calls_snapshot, status)` → `scores(run_id, criterion, value, reasoning)`; optional compaction of a volume's objects into Parquet for bulk evaluation/analytics (DuckDB over S3).

### SDK public API

```python
aicontrol.init(endpoint="http://localhost:8000", app_name="my-bot")
with aicontrol.volume("alice-chat-42"): ...           # sync or async context manager
@aicontrol.volume("support")                          # decorator (sync + async)
aicontrol.set_volume("x")                             # per-request (e.g. middleware)
aicontrol.wrap_context(fn) / aicontrol.run_in_thread(fn, ...)  # carry volume into threads
aicontrol.flush(); aicontrol.shutdown()
```

### Repository layout

```
AIControl/
├── docker-compose.yml                  # postgres:16 + minio (pinned tag) + bucket init, healthchecks
├── README.md
├── sdk/                                # pip-installable library: `aicontrol`
│   ├── pyproject.toml
│   ├── src/aicontrol/
│   │   ├── __init__.py                 # public API
│   │   ├── _config.py                  # init(), provider/exporter setup
│   │   ├── _volume.py                  # volume() / set_volume()
│   │   ├── _processor.py               # VolumeSpanProcessor
│   │   ├── _context.py                 # wrap_context / run_in_thread
│   │   └── _instrument.py              # OpenAI instrumentation
│   └── tests/
├── api/                                # FastAPI application (run, not installed)
│   ├── pyproject.toml                  # dependencies only
│   ├── alembic.ini
│   ├── alembic/                        # migrations
│   ├── app/
│   │   ├── main.py                     # FastAPI app, mounts routers + UI + static
│   │   ├── config.py                   # pydantic-settings (DATABASE_URL, S3_*)
│   │   ├── db.py                       # async engine / session
│   │   ├── models.py                   # SQLAlchemy models (index)
│   │   ├── repository.py               # Postgres data access
│   │   ├── storage/                    # ── heavy trace storage ──
│   │   │   ├── base.py                 # TraceStore interface + key builder
│   │   │   ├── s3.py                   # S3TraceStore (aioboto3; MinIO / AWS S3 / GCS)
│   │   │   └── memory.py               # InMemoryTraceStore (unit tests)
│   │   ├── services/
│   │   │   └── calls.py                # store call (S3 then DB), load full trace, export volume
│   │   ├── schemas.py                  # Pydantic response models
│   │   ├── views.py                    # new_messages(), export formatting
│   │   ├── ingest/
│   │   │   ├── otlp.py                 # OTLP protobuf/JSON decoding
│   │   │   └── mapper.py               # span -> trace document + index row
│   │   ├── routes/
│   │   │   ├── ingest.py               # POST /v1/traces
│   │   │   └── read.py                 # GET /api/...
│   │   └── ui/                         # ── Web UI (Jinja + HTMX) ──
│   │       ├── routes.py               # GET /, /volumes/{name}, HTMX partial endpoints
│   │       ├── templates/
│   │       │   ├── base.html           # layout, loads htmx from CDN
│   │       │   ├── volumes.html        # list of volumes
│   │       │   ├── volume_timeline.html# timeline page + time filter
│   │       │   └── partials/
│   │       │       ├── calls.html      # call rows (new messages, model, tokens, latency)
│   │       │       └── call_full.html  # full input/output of one call (from S3)
│   │       └── static/
│   │           └── app.css
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── e2e/
├── examples/
│   ├── openai_chat.py                  # multi-turn CLI chat with a tool, using aicontrol.volume (OpenAI or local Ollama via base_url)
│   └── fastapi_app.py                  # middleware setting volume from a header
└── .claude/features/llm-telemetry-sdk/
    ├── llm-telemetry-sdk-plan.md       # this plan
    └── llm-telemetry-sdk-implementation.md  # implementation log (created by /implement-plan)
```

## Implementation Tasks

### Task 1: Scaffold + infrastructure + Ollama compatibility spike

**Files to modify/create**:
- `sdk/pyproject.toml`, `api/pyproject.toml` – two uv projects (Python ≥3.11), ruff, pytest
- `docker-compose.yml` – Postgres 16 and MinIO (pinned image tag), a one-shot bucket-init container (`mc mb aicontrol-traces`), named volumes, healthchecks
- `.env.example`, `.gitignore`, `README.md` – skeleton

**Implementation**:
1. Create both uv projects and dev dependencies.
2. Add Docker Compose for Postgres + MinIO + bucket init.
3. Spike test: latest `ollama` + `opentelemetry-instrumentation-ollama`, mocked Ollama HTTP via `respx`, spans captured by `InMemorySpanExporter`. If incompatible, pin the newest working `ollama` and document why (instrumentor tests pin 0.4.x; latest `ollama` is 0.6.2 as of 2026-09-24).

**Tests** (implement alongside):
- [x] Unit test: spike captures an `ollama.chat` span with prompt, completion, model and token attributes.

**Acceptance criteria**:
- [x] `uv run pytest` passes in `sdk/` and `api/`.
- [x] `docker compose up -d` yields healthy Postgres and MinIO with bucket `aicontrol-traces` created.
- [x] `ollama` version and MinIO image tag pinned with rationale.

**Completion Notes**:
- **Files created**: `.gitignore`, `.env.example`, `docker-compose.yml`, `README.md`; `sdk/{pyproject.toml,.python-version,README.md,src/aicontrol/__init__.py,tests/test_ollama_compat_spike.py}`; `api/{pyproject.toml,.python-version,app/__init__.py,app/main.py,tests/__init__.py,tests/unit/test_health.py}`; empty `api/tests/{integration,e2e}/`, `examples/`.
- **Key decisions**:
  - Python pinned to 3.12 via `.python-version` (`requires-python >=3.11`); system default is 3.14, avoided for OTel package compatibility.
  - `ollama` 0.6.2 (latest) **is compatible** with `opentelemetry-instrumentation-ollama` 0.62.3 → pinned `ollama>=0.6,<0.7`, instrumentor `>=0.62,<0.63`. No downgrade needed.
  - `ollama` is an optional SDK extra (`aicontrol[ollama]`) and a dev dependency, not a hard dependency.
  - MinIO is **gone from Docker Hub**; images pinned to `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` and `quay.io/minio/mc:RELEASE.2025-08-13T08-35-41Z` (last community releases, anonymous pull OK).
  - Default host ports changed to **Postgres 5442, MinIO S3 9100, console 9101** because another local stack already uses 9000/9001.
  - `api/` is an application: `[tool.uv] package = false`, `pythonpath = ["."]` in pytest so tests import `app.*`.
  - Added a minimal `GET /health` in `api/app/main.py` so the API project has a runnable app and a passing test.
- **Patterns established**: pytest `asyncio_mode = "auto"`; ruff (line 100, rules E,F,I,UP,B) in both projects; Ollama mocked with `respx` against host `http://ollama.test:11434`; spans captured with `InMemorySpanExporter` + `SimpleSpanProcessor`.
- **Integration points**: `DATABASE_URL` and `S3_*` env names defined in `.env.example` (to be read by `api/app/config.py` in Task 4).
- **Revision (2026-09-24)**: provider switched to OpenAI; the Ollama spike test and dependencies are replaced in Task 3.
- **Notes for next task**: Instrumentor span name is `ollama.chat`; attributes verified: `gen_ai.request.model`, `gen_ai.prompt.N.role/content`, `gen_ai.completion.0.role/content`, `gen_ai.usage.input_tokens/output_tokens`. On this machine `docker compose` plugin is broken → use `docker-compose`.

**Status**: Completed

### Task 2: SDK core — init, volume context, span processor

**Files to modify/create**:
- `sdk/src/aicontrol/__init__.py`, `_config.py`, `_volume.py`, `_processor.py`, `_context.py`

**Implementation**:
1. `init(endpoint, app_name)`: TracerProvider with `service.name` resource, `VolumeSpanProcessor`, `BatchSpanProcessor(OTLPSpanExporter(endpoint + "/v1/traces"))`. Idempotent.
2. `volume(name)`: one object usable as sync/async context manager and sync/async decorator; contextvar with token reset.
3. `set_volume()`, `wrap_context()` / `run_in_thread()`, `flush()`, `shutdown()`, `atexit` flush.
4. `VolumeSpanProcessor.on_start` sets `aicontrol.volume` (fallback `"default"`).

**Tests** (InMemorySpanExporter):
- [x] Unit test: no volume → spans carry `default`.
- [x] Unit test: nested volumes restore the outer one on exit.
- [x] Unit test: 50 concurrent asyncio tasks with different volumes never mix.
- [x] Unit test: threads get the right volume with `wrap_context`; documents fallback without it.
- [x] Unit test: sync and async decorators.
- [x] Unit test: double `init()` does not add a second exporter.

**Acceptance criteria**:
- [x] No global mutable volume state.
- [x] All tests pass.

**Completion Notes**:
- **Files created**: `sdk/src/aicontrol/{_config,_volume,_processor,_context}.py`, updated `__init__.py`; tests `sdk/tests/{__init__,conftest,test_init,test_volume,test_context}.py`.
- **Key decisions**:
  - The SDK uses **its own `TracerProvider`** and never calls `trace.set_tracer_provider()`, so it doesn't hijack an app's existing OTel setup. Task 3 must pass `_config.get_tracer_provider()` to `OllamaInstrumentor().instrument(tracer_provider=...)`.
  - `init(endpoint, app_name, *, span_exporter=None, batch=True)`: `span_exporter` overrides the OTLP exporter (tests); `batch=False` → `SimpleSpanProcessor`. A second `init()` logs a warning and returns the existing provider. `shutdown()` resets state so `init()` can be called again. `atexit` registers `shutdown` once.
  - Resource attributes: `service.name=<app_name>`, `aicontrol.sdk.version`.
  - Volume attribute key: `aicontrol.volume` (`VOLUME_ATTRIBUTE`); default `"default"` (`DEFAULT_VOLUME`) is stamped on every span, so the API always receives a volume.
  - `volume(name)` class: sync/async context manager + sync/async decorator; decorator creates a fresh scope per call (safe for concurrent calls). Names must be non-empty strings (`ValueError`); URL-safety sanitisation is the API's job (Task 5).
  - Added beyond plan: `current_volume()` and `reset_volume(token)` (`set_volume` returns a token) — small, needed for tests and middleware cleanup.
  - `run_in_thread(fn, *args, **kwargs)` returns a `concurrent.futures.Future`; `wrap_context(fn)` for thread pools. `asyncio.to_thread` already propagates context (tested).
- **Public API** (`aicontrol.*`): `init`, `flush`, `shutdown`, `volume`, `set_volume`, `reset_volume`, `current_volume`, `wrap_context`, `run_in_thread`, `DEFAULT_VOLUME`.
- **Test utilities added**: `tests/conftest.py` fixtures `exporter` (inits SDK with `InMemorySpanExporter`, `batch=False`, shuts down after) and `tracer`; helper `volumes_by_span_name(exporter)`.
- **Notes for next task**: `test_ollama_compat_spike.py` still builds its own provider; Task 3 tests should use the `exporter` fixture so spans go through `VolumeSpanProcessor`. Remember to `uninstrument()` in teardown since `init()` can run many times per test session.

**Status**: Completed

### Task 3: SDK OpenAI capture (Chat Completions)

**Files to modify/create**:
- `sdk/pyproject.toml` – replace `opentelemetry-instrumentation-ollama` with `opentelemetry-instrumentation-openai>=0.62,<0.63`; extra `openai = ["openai>=3,<4"]`; `openai` as dev dependency; drop `ollama` and `respx`
- `sdk/src/aicontrol/_instrument.py` – instrument / uninstrument OpenAI
- `sdk/src/aicontrol/_config.py` – call instrumentation in `init()`, uninstrument in `shutdown()`
- `sdk/tests/test_openai_capture.py`, `sdk/tests/fixtures/openai_responses.py`
- delete `sdk/tests/test_ollama_compat_spike.py`

**Implementation**:
1. `init(..., instrument=True)` calls `OpenAIInstrumentor().instrument(tracer_provider=<SDK provider>)`; `shutdown()` calls `uninstrument()` so a later `init()` binds to the new provider.
2. If `openai` is not installed, log a warning and skip.
3. Message content capture stays on (OpenLLMetry default, `TRACELOOP_TRACE_CONTENT=true`); document how to turn it off.

**Tests** (OpenAI mocked via `httpx.MockTransport` injected with `http_client=`; no network):
- [x] Unit test: sync chat — input/output messages, request settings, response model/id, finish reasons, tokens incl. cached and reasoning, volume on span.
- [x] Unit test: streaming chat (`stream=True`, `stream_options={"include_usage": True}`) — one span after the stream is consumed, full reply text, usage.
- [x] Unit test: `AsyncOpenAI` chat with correct volume.
- [x] Unit test: tool call in the reply captured in `gen_ai.output.messages`; tool definitions captured; tool round-trip (assistant tool_call + tool result) captured in input.
- [x] Unit test: OpenAI error (e.g. 429) → span status error with `error.type`; the original exception reaches the app unchanged.
- [x] Unit test: AIControl API unreachable → the OpenAI call returns normally, no exception in the app.
- [x] Unit test: OpenAI-compatible `base_url` (e.g. local Ollama) is captured with its `api_base`.
- [ ] **(pending OPENAI_API_KEY)** Live test (`e2e`, real OpenAI, no mocks): a real `gpt-4o-mini` chat with a tool produces a span with messages, tool call, tokens and volume.

**Acceptance criteria**:
- [x] OpenAI spans carry everything the API needs (messages incl. tool calls + monitoring attributes).
- [x] `openai` 3.x compatibility verified and version pinned with rationale.

**Completion Notes**:
- **Files created/modified**: `sdk/pyproject.toml` (deps swapped to OpenAI; pytest `e2e` marker, `addopts = -m 'not e2e'`, warning filter), `sdk/src/aicontrol/_instrument.py` (new), `sdk/src/aicontrol/_config.py` (`instrument=True` param), `sdk/tests/fixtures/{__init__,openai_responses}.py`, `sdk/tests/test_openai_capture.py`, `sdk/tests/test_openai_live.py`; deleted `sdk/tests/test_ollama_compat_spike.py`; `README.md`, `.env.example` (OPENAI_API_KEY, AICONTROL_E2E_MODEL).
- **Key decisions**:
  - **Upstream bug worked around**: `OpenAIInstrumentor.uninstrument()` (0.62.3) does not unwrap on `openai` 3.x — it passes dotted attrs like `"Completions.create"` to OTel `unwrap()`, which can't resolve them — so each instrument cycle stacked a wrapper. The SDK now instruments **once per process** against a `_DelegatingTracerProvider` that forwards each span to the SDK's *current* provider (no-op after `shutdown()`). No uninstrument is ever needed. Consequence: `init(instrument=False)` after an earlier instrumented `init()` in the same process still captures.
  - `openai` 3.x uses **`httpx2`**, not `httpx`; `respx` cannot intercept it. Tests inject `httpx2.MockTransport` via `http_client=` with a non-routable `base_url` (`http://openai.test/v1`) and `max_retries=0`. `respx` and `ollama` removed.
  - `openai` is an optional extra (`aicontrol[openai]`) + dev dependency.
  - Content capture stays on by default (`TRACELOOP_TRACE_CONTENT`), documented in README.
  - Live tests: marker `e2e`, excluded by default; key from env or root `.env`; skip with explicit reason if absent; model via `AICONTROL_E2E_MODEL` (default `gpt-4o-mini`).
- **Attributes verified on `openai.chat` spans** (for the Task 6 mapper): `gen_ai.provider.name`, `gen_ai.operation.name`, `gen_ai.request.{model,temperature,max_tokens,top_p}`, `gen_ai.response.{model,id,finish_reasons}` (finish reason for tool calls is normalised to `"tool_call"`), `gen_ai.usage.{input_tokens,output_tokens,total_tokens,cache_read.input_tokens,reasoning_tokens}`, `gen_ai.is_streaming`, `gen_ai.openai.api_base` (trailing `/`), `gen_ai.tool.definitions` (JSON list of `{type,name,description,parameters}`), `gen_ai.input.messages` / `gen_ai.output.messages` (JSON lists of `{role, parts[, finish_reason]}`; part types `text` `{content}`, `tool_call` `{id,name,arguments(dict)}`, `tool_call_response` `{id, response?}`), `error.type` on failures, plus `openai.response.service_tier`, `gen_ai.openai.response.system_fingerprint`.
- **Test utilities added**: `tests/fixtures/openai_responses.py` — `client()/async_client()` with mock transport, `json_handler`, `sse_handler`, `stream_body()`, canned `TEXT_REPLY`, `TOOL_CALL_REPLY`, `WEATHER_TOOL`, `USAGE`.
- **Notes for next task**: Task 6's JSON-payload integration test can reuse these fixtures to produce realistic spans. The live test is written but not yet run (needs the user's key).

**Status**: Completed (live e2e test pending OPENAI_API_KEY)

### Task 4: API index database (Postgres + Alembic)

**Files to modify/create**:
- `api/app/config.py`, `api/app/db.py`, `api/app/models.py`, `api/app/repository.py`
- `api/alembic.ini`, `api/alembic/` + initial migration

**Implementation**:
1. pydantic-settings with `DATABASE_URL` and `S3_*` settings.
2. Async SQLAlchemy models per the data model (index only, no heavy JSON); initial Alembic migration.
3. Repository: `upsert_volume`, `insert_calls` (`ON CONFLICT DO NOTHING`, updates `last_activity_at`), `list_volumes`, `list_calls(volume, from, to, limit, cursor)`, `get_call`, `list_calls_until(volume, until)`.

**Tests** (testcontainers Postgres):
- [x] Integration test: migrations apply cleanly.
- [x] Integration test: duplicate `(trace_id, span_id)` ignored.
- [x] Integration test: volume auto-created on first call.
- [x] Integration test: time filters (`from` inclusive, `to` exclusive).
- [x] Integration test: stable cursor pagination ordered by `started_at`.

**Acceptance criteria**:
- [x] Repository fully covered against real Postgres.

**Completion Notes**:
- **Files created/modified**: `api/pyproject.toml` (deps: alembic, psycopg[binary], pydantic-settings, sqlalchemy[asyncio]; dev: testcontainers[postgres], `httpx2` replaces `httpx`; ruff isort `known-third-party = ["alembic"]`), `api/app/{config,db,models,repository}.py`, `api/alembic.ini`, `api/alembic/{env.py,script.py.mako,README}`, `api/alembic/versions/2026_09_24_1530-4ec62d3af38f_create_volumes_and_llm_calls.py`, `api/tests/conftest.py`, `api/tests/{unit,integration}/__init__.py`, `api/tests/integration/{conftest,test_migrations,test_repository}.py`, `README.md`.
- **Key decisions**:
  - `Settings` (pydantic-settings) reads env vars and the **root `.env`** (`ROOT_DIR/.env`); defaults match docker-compose (Postgres `localhost:5442`, MinIO `http://localhost:9100`). `get_settings()` is `lru_cache`d.
  - Alembic uses the async template; `env.py` takes `sqlalchemy.url` from the Alembic config if set (tests) else from `get_settings().database_url`. Migration file names are date-prefixed.
  - Models per the plan's data model; ids are `BIGINT IDENTITY`; `volumes.metadata` column mapped as `Volume.metadata_`; `finish_reasons`/`tool_calls_made` are `TEXT[]`; `LlmCall.volume` relationship is eager (`lazy="joined"`) so `call.volume.name` works in async code.
  - Repository is plain async functions taking an `AsyncSession`; **the caller owns the transaction** (commit/rollback) — Task 5's `store_call()` should commit after the S3 put.
  - `NewCall` frozen dataclass = the index row the mapper must produce (Task 6); field names equal column names (+ `volume` name instead of `volume_id`).
  - `insert_calls` upserts volumes first (`last_activity_at = GREATEST(old, new)`), then `INSERT … ON CONFLICT (uq_llm_calls_trace_span) DO NOTHING RETURNING id`; returns the number of new rows.
  - `list_calls` is **chronological** (oldest first) with keyset pagination on `(started_at, id)`; cursor = urlsafe base64 of `"<iso started_at>|<id>"`. An empty page keeps the incoming cursor, so the UI can poll with the same cursor to get only new calls. Bad cursor → `InvalidCursorError` (map to 400 in Task 7).
  - `list_calls_until(volume, until)` is inclusive (`started_at <= until`) for exports.
  - Testcontainers + Colima: `api/tests/conftest.py` sets `DOCKER_HOST` from `docker context inspect` and `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock` when `DOCKER_HOST` is unset.
- **Test utilities added**: `tests/integration/conftest.py` — session-scoped `postgres_url` (Postgres 16 container, migrations applied), per-test `session` (TRUNCATE + fresh engine), `alembic_config(url)`; `tests/integration/test_repository.py` helpers `make_call(...)`, `spans(n, ...)`.
- **Notes for next task**: Local compose DB is migrated to head (`4ec62d3af38f`). Task 5 will need a MinIO testcontainer (`testcontainers[minio]` extra) alongside `postgres_url`.

**Status**: Completed

### Task 5: Trace object storage (S3 / MinIO)

**Files to modify/create**:
- `api/app/storage/base.py` – `TraceStore` protocol (`put(key, doc)`, `get(key)`, `list_prefix(prefix)`) + `build_trace_key(volume, started_at, trace_id, span_id)`
- `api/app/storage/s3.py` – `S3TraceStore` on `aioboto3` with configurable `endpoint_url`
- `api/app/storage/memory.py` – `InMemoryTraceStore`
- `api/app/services/calls.py` – `store_call()` (S3 put → DB insert), `load_trace()`, `export_volume()`

**Implementation**:
1. Key builder: percent-encode volume names into one key segment (any name accepted; `/` and dot-only names escaped), UTC date path, deterministic file name.
2. `S3TraceStore`: JSON serialize (UTF-8, `Content-Type: application/json`), gzip optional later; bounded-concurrency `get_many` for exports.
3. `store_call()`: put object first, then index row; on S3 failure raise → ingest returns 5xx so the exporter retries.
4. `export_volume(name, until)`: index rows up to cutoff → fetch objects concurrently → ordered list + snapshot (call IDs, cutoff).

**Tests**:
- [x] Unit test: key builder — layout, UTC date, encoding keeps every volume in its own segment, rejects invalid lengths.
- [x] Unit test (in-memory store): `store_call` writes object then row; S3 failure → no row written, error raised.
- [x] Integration test (testcontainers MinIO): put/get roundtrip; `list_prefix("volumes/alice-chat-42/")` returns only that volume; re-put same key overwrites (idempotent).
- [x] Integration test (Postgres + MinIO): `export_volume` returns full traces in order with a snapshot matching the included IDs.

**Acceptance criteria**:
- [x] Switching MinIO → AWS S3 requires only `S3_*` env changes (documented in README, incl. GCS HMAC interoperability endpoint).
- [x] No heavy trace content stored in Postgres beyond the preview.

**Completion Notes**:
- **Files created/modified**: `api/pyproject.toml` (+ `aioboto3>=15.5,<16`), `api/app/storage/{__init__,base,memory,s3}.py`, `api/app/services/{__init__,calls}.py`, `api/tests/unit/test_trace_keys.py`, `api/tests/integration/conftest.py` (+ MinIO fixtures), `api/tests/integration/{test_s3_store,test_calls_service}.py`, `README.md` (Trace storage section).
- **Key decisions**:
  - **Volume names are percent-encoded into the key instead of rejected** (the SDK accepts any string; rejecting at ingest would lose data): `quote(name, safe="-_~@:.")`, and dot-only names (`.`, `..`) become `%2E…`. Readable for normal names (`alice-chat-42`, `user@example.com`); `a/b` → `a%2Fb`; one segment always. Only length 1–255 is enforced (`ValueError`). Postgres keeps the original name. Use `volume_prefix(name)` to list a volume.
  - `TraceStore` protocol: `put(key, doc) -> size_bytes`, `get(key)` (→ `TraceNotFoundError`), `get_many(keys)` (ordered), `list_prefix(prefix)` (sorted, paginated). Serialization: compact UTF-8 JSON, `default=str` (datetimes become strings).
  - `S3TraceStore(bucket, endpoint_url=, access_key=, secret_key=, region=, max_concurrency=16)`: one aioboto3 client kept open between `start()`/`close()` (or `async with`); path-style addressing; bounded concurrency via semaphore; `ensure_bucket()` creates the bucket if missing. Using it before `start()` raises `RuntimeError`.
  - `services.calls.store_calls(session, store, [CallToStore(row, trace)])`: derives the key from the row (row's `trace_key` ignored), puts **all** objects concurrently, then inserts rows and **commits**; on S3 failure nothing reaches Postgres and the error propagates; DB failure → rollback + raise. Returns new-row count (retries count 0).
  - `export_volume(session, store, volume, until)` → `VolumeExport(volume, until, calls=[{"id", **trace}], snapshot={volume, until (iso), call_count, call_ids})`.
  - MinIO testcontainer uses a generic `DockerContainer` with the **same pinned quay.io image** as compose (the testcontainers MinIO module needs the `minio` package and defaults to a Docker Hub image that no longer exists). Each test gets a fresh bucket.
- **Test utilities added**: fixtures `minio_endpoint` (session) and `s3_store` (started store on a unique bucket); `InMemoryTraceStore` (`.objects` dict of bytes) for fast tests; `to_store()` / `FailingStore` in `test_calls_service.py`.
- **Notes for next task**: Task 6's ingest route needs the app to hold a started `S3TraceStore` and a session factory (FastAPI lifespan) — build them from `get_settings()`; call `store_calls()` per request batch; map `TraceNotFoundError`/S3 errors to 5xx for retries. The mapper must return `CallToStore(row=NewCall(...), trace={...})`.

**Status**: Completed

### Task 6: OTLP ingest endpoint

**Files to modify/create**:
- `api/app/ingest/otlp.py`, `api/app/ingest/mapper.py`, `api/app/routes/ingest.py`

**Implementation**:
1. `POST /v1/traces` accepts `application/x-protobuf` (via `opentelemetry-proto`) and `application/json`; handles `Content-Encoding: gzip`.
2. Keep only LLM spans: those with `gen_ai.operation.name`, `gen_ai.provider.name` or `gen_ai.request.model`.
3. Mapper produces (a) the full trace document (S3) — `input_messages` / `output_messages` parsed from the `gen_ai.input.messages` / `gen_ai.output.messages` JSON and normalised (`text` parts → `content`, `tool_call` parts → `tool_calls`, `tool_call_response` parts → tool message with `tool_call_id`), `tool_definitions`, all raw attributes, resource; (b) the index row with the monitoring columns and `preview = new_messages(...)`.
4. Read `aicontrol.volume` (fallback `default`); `app_name` from resource `service.name`.
5. Persist via `services.calls.store_call()`. Malformed spans are logged and skipped; storage failures → 5xx for retry.
6. Return `ExportTraceServiceResponse`.

**Tests**:
- [x] Integration test: protobuf payload encoded by the real OTel exporter → object in MinIO + index row in Postgres.
- [x] Integration test: equivalent JSON payload is stored.
- [x] Unit test: non-LLM spans ignored.
- [x] Unit test: missing volume → `default`.
- [x] Unit test: message parts normalised — text, tool_call (reply), tool_call_response (input).
- [x] Unit test: monitoring attributes promoted to index columns (models, tokens incl. cached/reasoning, finish reasons, settings, tools offered / tool calls made, error type).
- [x] Unit test: missing or invalid messages JSON → call stored with empty messages and a warning, not dropped.
- [x] Integration test: malformed span → no 500, other spans stored.
- [x] Integration test: gzip body accepted.
- [x] Integration test: same batch sent twice → one object, one row.

**Acceptance criteria**:
- [x] Real SDK batches stored with correct volume: full trace in S3, index in Postgres.

**Completion Notes**:
- **Files created/modified**: `api/pyproject.toml` (+ `opentelemetry-proto`; dev: local `aicontrol` SDK (editable path source) and `openai`; warning filter), `api/app/ingest/{__init__,otlp,mapper}.py`, `api/app/views.py` (`new_messages`), `api/app/deps.py`, `api/app/routes/{__init__,ingest}.py`, `api/app/main.py` (now `create_app()` + lifespan), `api/alembic/env.py` (logging fix), `api/tests/spans.py`, `api/tests/unit/{test_otlp,test_mapper,test_views}.py`, `api/tests/integration/test_ingest.py`, `api/tests/integration/conftest.py` (+ `session_factory` fixture).
- **Key decisions**:
  - `otlp.decode_request(body, content_type, content_encoding)` → list of plain `Span` dataclasses (hex ids, UTC datetimes with µs, python attribute values, resource, scope, events, status `unset|ok|error` + message). Handles protobuf, **OTLP/JSON (hex ids converted before protobuf JSON parsing)**, gzip/deflate; anything undecodable → `OtlpDecodeError`.
  - Route behaviour: bad body → **400** (exporters don't retry); non-LLM spans ignored; a malformed LLM span is skipped and reported in the standard OTLP `partial_success.rejected_spans` / `error_message` (200); storage failure → **503** so the exporter retries the whole batch (safe: storage is idempotent). Response is protobuf or JSON matching the request.
  - LLM span = has `gen_ai.operation.name`, `gen_ai.provider.name` or `gen_ai.request.model`.
  - Mapper normalises messages to `{role, content, tool_calls?[{id,name,arguments}], tool_call_id?, finish_reason?, parts?}` (`tool_call_response.response` → tool message `content`; unknown part types kept in `parts`). Invalid messages JSON → empty list + warning, call still stored. Invalid/missing volume → `default` + warning. Bad ids or no start time → `MappingError`.
  - Trace document (S3) fields: `schema_version, volume, trace_id, span_id, span_name, scope, app_name, started_at, ended_at, latency_ms, status, status_message, error_type, operation, provider, request_model, response_model, api_base, response_id, streaming, request{temperature,max_tokens,top_p}, tokens{input,output,total,cached_input,reasoning}, finish_reasons, input_messages, output_messages, tool_definitions, events, raw_attributes, resource`.
  - **`new_messages()` implemented here** (needed for the ingest preview) in `app/views.py`, with its unit tests (first turn, turn N, tool-call reply, tool round trip, failed call) — Task 7's `new_messages` test item is therefore already covered.
  - `app.main.create_app(session_factory=None, trace_store=None)`: injected dependencies are used as-is (tests); otherwise the lifespan builds the engine + started `S3TraceStore` from settings and closes them on shutdown. `app = create_app()` for `fastapi run`. Dependencies `get_session` / `get_store` in `app/deps.py` read `app.state`.
  - **Bug fixed**: Alembic's `env.py` called `fileConfig()` with the default `disable_existing_loggers=True`, silencing app loggers whenever migrations ran in-process (caught by a mapper warning test failing only in the full run).
- **Test utilities added**: `tests/spans.py` — genuine spans via the SDK + OpenAI instrumentor + `httpx2.MockTransport`: `capture(*calls)`, `chat(reply=, messages=, volume=, **kwargs)`, `failing_chat()`, encoders `to_request/to_protobuf/to_otlp_json`, `with_broken_span_id()`, canned `TEXT_REPLY`, `TOOL_CALL_REPLY`, `TOOL_ROUND_TRIP`, `WEATHER_TOOL`. Integration fixture `session_factory`; `client_for(session_factory, store)` pattern with `httpx2.AsyncClient(transport=httpx2.ASGITransport(app))`.
- **Manual smoke test**: `fastapi run app/main.py --port 8077` against compose Postgres + MinIO, SDK with the real batched OTLP exporter → 2 rows + 2 objects in volume `smoke-test` (left in the local dev DB/bucket). Port 8000 was occupied by another local process.
- **Notes for next task**: read routes go in `app/routes/read.py`, included in `create_app()`; map `repository.InvalidCursorError` → 400 and `storage.base.TraceNotFoundError` → a clear error; `LlmCall.preview` already holds the new messages; full traces via `services.calls.load_trace()` / `export_volume()`.

**Status**: Completed

### Task 7: REST read API + export

**Files to modify/create**:
- `api/app/routes/read.py`, `api/app/schemas.py`, `api/app/views.py`

**Implementation**:
1. `GET /api/volumes`
2. `GET /api/volumes/{name}/calls?from=&to=&limit=&cursor=` (index + preview, Postgres only)
3. `GET /api/calls/{id}` (index + full trace loaded from S3)
4. `GET /api/volumes/{name}/export?until=&format=json|text` (ordered full traces + snapshot)
5. `new_messages(call)`: input messages after the last `assistant` message + output.

**Tests**:
- [x] Unit test: `new_messages` — first turn, turn N, reply that is a tool call, tool round-trip. *(done in Task 6)*
- [x] Integration test: 404 for unknown volume / call; clear error if the S3 object is missing.
- [x] Integration test: text export reads as an ordered transcript.
- [x] Integration test: `until` excludes later calls.

**Acceptance criteria**:
- [x] Responses match schemas.
- [x] Export is ready to feed an evaluator.

**Completion Notes**:
- **Files created/modified**: `api/app/schemas.py`, `api/app/routes/read.py`, `api/app/views.py` (+ `format_transcript`), `api/app/main.py` (includes `read.router`), `api/tests/integration/test_read_api.py`, `api/tests/unit/test_views.py`.
- **Endpoints**:
  - `GET /api/volumes` → `[VolumeOut{name, call_count, created_at, last_activity_at}]` (most recent first).
  - `GET /api/volumes/{name}/calls?from=&to=&limit=1..500(50)&cursor=` → `CallPageOut{volume, items: [CallSummary], next_cursor, has_more}`; 404 unknown volume, 400 bad cursor, 422 bad params.
  - `GET /api/calls/{id}` → `CallDetail` = summary + `trace` (full S3 document) + `trace_error`; 404 unknown call.
  - `GET /api/volumes/{name}/export?until=&format=json|text` → `VolumeExportOut{volume, until, snapshot, calls}` or a text transcript; `until` defaults to now.
- **Key decisions**:
  - Volume routes use `{name:path}` so names containing `/` work, both raw and `%2F`-encoded.
  - `CallSummary` = index data only (no S3 read) with `tokens{input,output,total,cached_input,reasoning}` and `new_messages` (= stored preview).
  - Missing S3 object: `GET /api/calls/{id}` degrades gracefully (`trace: null`, `trace_error` message, index data still returned); **export fails with 502** ("Export incomplete") so an evaluation never runs on partial data.
  - Datetime query params without a timezone are treated as UTC.
  - Text transcript = each call's new messages (no repeated history): header per call with id, time, model, tokens, status; `[role] text`, `[assistant -> tool call <id>] name({args})`, `[tool <id>] result`, `[error] type: message`.
- **Test utilities added**: `test_read_api.py` fixtures — `client` (app with injected session factory + in-memory store, seeded through the real `/v1/traces` with a genuine tool conversation in `alice-chat-42` and a call in `team/support`), `seed_timed()` for fixed timestamps.
- **Manual smoke test**: real server on :8077 against compose — `/api/volumes`, `/calls`, `/api/calls/{id}` (trace loaded from MinIO) and text export all OK.
- **Notes for next task (UI)**: reuse `repository` + `CallSummary.of()` / `CallDetail`; the timeline can poll `list_calls(cursor=next_cursor)` (an empty page keeps the cursor); tool calls are in `new_messages[*].tool_calls`; UI routes/templates go in `app/ui/` and must be included in `create_app()`.

**Status**: Completed

### Task 8: Web UI (Jinja + HTMX) — `api/app/ui/`

**Files to modify/create**:
- `api/app/ui/routes.py`
- `api/app/ui/templates/base.html`, `volumes.html`, `volume_timeline.html`
- `api/app/ui/templates/partials/calls.html`, `partials/call_full.html`
- `api/app/ui/static/app.css`
- `api/app/main.py` – mount UI router and `/static`

**Implementation**:
1. `/`: volumes table (name, call count, last activity).
2. `/volumes/{name}`: timeline of calls rendered from Postgres previews (new messages as chat bubbles, tool calls shown as badges + response model, tokens incl. cached/reasoning, latency, finish reason, status, time); time-range filter (`hx-get` on form change); auto-refresh appending new calls (`hx-trigger="every 2s"`, `hx-swap="beforeend"`).
3. "Show full input" loads `partials/call_full.html` (trace fetched from S3) into the call row.
4. HTMX loaded from CDN; no JS build.

**Tests** (TestClient HTML assertions):
- [x] Integration test: volumes page lists seeded volumes.
- [x] Integration test: timeline shows only new messages and does not call S3.
- [x] Integration test: full-input partial shows all messages from the stored object.
- [x] Integration test: time filter narrows results.
- [x] Integration test: empty states render.

**Acceptance criteria**:
- [x] With the API running, calls sent by the SDK are visible at `http://localhost:8000`.

**Completion Notes**:
- **Files created/modified**: `api/app/ui/{__init__,routes}.py`, `api/app/ui/templates/{base,volumes,volume_timeline}.html`, `api/app/ui/templates/partials/{calls,call_full}.html`, `api/app/ui/static/app.css`, `api/app/main.py` (UI router + `/static` mount), `api/tests/integration/test_ui.py`.
- **Routes**: pages `GET /` (volumes) and `GET /volumes/{name:path}` (timeline, `?from=&to=` as UTC `datetime-local`); HTMX fragments `GET /ui/calls?volume=&cursor=&from=&to=` (next rows + next trailing element) and `GET /ui/calls/{id}/full` (full trace from S3). Fragments are under `/ui/` so volume names with `/` can't collide.
- **Key decisions**:
  - One trailing `<li>` drives loading: a **"Load more"** button while `has_more` (page size 50), otherwise a **poller** (`hx-trigger="every 2s"`, `hx-swap="outerHTML"`); each response returns new rows + the next element with the updated cursor, so new calls append at the bottom in chronological order.
  - Timeline renders from Postgres only (`CallSummary` previews); S3 is read only for "Show full input" (verified by a test store that counts reads).
  - Message content is untrusted: Jinja autoescape; XSS test. htmx **2.0.11 pinned from jsDelivr with SRI** (`sha384-2Oatz…`).
  - Filters: plain GET form (no JS needed); invalid date → 400; unknown volume → 404.
  - CSS: system fonts, light/dark via `prefers-color-scheme`, role-coloured message blocks, tool-call badges, red border for error calls.
- **Visual check**: headless Chrome screenshots of `/` and `/volumes/demo-conversation` (local dev data: 4-call demo with tool call, tool result, follow-up, rate-limit error) — layout as intended; fixed "1 tools" → "1 tool".
- **Test utilities added**: `NoReadStore` (counts S3 reads), `store_messages()` with a global span-id counter, `call_ids(html)`.
- **Notes for next task**: local dev DB/bucket now contain volumes `smoke-test` (2 calls) and `demo-conversation` (4 calls). Port 8000 is used by another local process on this machine — the README quickstart should mention `--port` or use a free port.

**Status**: Completed

### Task 9: End-to-end verification, examples, docs

**Files to modify/create**:
- `examples/openai_chat.py`, `examples/fastapi_app.py`
- `api/tests/e2e/test_sdk_to_api.py` (SDK installed from `../sdk` as dev dependency)
- `README.md`

**Implementation**:
1. E2E (**no mocks**, marker `e2e`): start the real API on a random port with Postgres + MinIO (testcontainers); the SDK and the **real OpenAI API** (`OPENAI_API_KEY`) across two volumes, a streamed call and a tool round-trip; `flush()`; assert via REST, export, and object listing under `volumes/<name>/`. Skipped with an explicit reason when the key is absent.
2. Optional: same flow against a local Ollama through its OpenAI-compatible endpoint (`http://localhost:11434/v1`), marker `ollama`.
3. README quickstart: `docker compose up -d` → `cd api && uv run alembic upgrade head && uv run fastapi dev app/main.py` → `uv run examples/openai_chat.py` (OpenAI key or `--base-url http://localhost:11434/v1`) → open `http://localhost:8000` (MinIO console to inspect objects). Document volumes, async/threads, FastAPI middleware, and how to point `S3_*` at AWS S3 or GCS.

**Tests**:
- [ ] **(pending OPENAI_API_KEY — harness dry-run passed)** E2E test (real OpenAI): calls land in the right volumes (objects in S3 + rows in Postgres) with complete messages, tool calls and monitoring columns.
- [ ] **(pending OPENAI_API_KEY — harness dry-run passed)** E2E test: concurrent FastAPI requests with different headers land in separate volumes.
- [ ] **(optional, pending)** E2E test: local Ollama-compatible run passes (same tests with `AICONTROL_E2E_BASE_URL=http://localhost:11434/v1`; Ollama isn't installed on this machine).

**Acceptance criteria**:
- [x] Anyone can reproduce the full loop locally from the README. *(each step verified: compose, migrations, server, examples start; the step that talks to a real model needs a key)*

**Completion Notes**:
- **Files created/modified**: `examples/openai_chat.py`, `examples/fastapi_app.py`, `api/tests/e2e/{__init__,conftest,test_sdk_to_api}.py`, `api/app/main.py` (`create_app(settings=...)`), `api/pyproject.toml` (`e2e` marker, `addopts = -m 'not e2e'`), `README.md` (quickstart, SDK usage, REST table, examples, tests), `.env.example` (`AICONTROL_E2E_BASE_URL`).
- **Key decisions**:
  - **E2E has no mocks**: real API server (uvicorn in a thread, random port, `create_app(settings=Settings(...))` pointing at testcontainers Postgres + MinIO with a fresh bucket), SDK with the production **batched** OTLP exporter, real OpenAI calls. Test 1: forced tool call → tool result → streamed follow-up in one volume + a call in a second volume; asserts via REST (counts, order, tool calls, tool results, streaming, monitoring columns incl. tokens/latency), full trace from S3, S3 keys per volume prefix, JSON + text export. Test 2: loads `examples/fastapi_app.py` and sends 4 **concurrent** requests with different `X-Chat-Id` → 4 separate volumes, each with its own user message.
  - Settings: `OPENAI_API_KEY` (env or root `.env`), `AICONTROL_E2E_MODEL` (default `gpt-4o-mini`), `AICONTROL_E2E_BASE_URL` (any OpenAI-compatible server; key optional then) — this replaces a separate Ollama test.
  - `api_server` depends on `llm`, so without a key the tests skip in ~1 s before any container starts.
  - Examples use **uv inline script metadata** with `[tool.uv.sources] aicontrol = { path = "../sdk" }` → `uv run examples/<file>.py` installs the local SDK automatically. CLI chat runs tools in a loop and shuts the SDK down on exit; the FastAPI example sets/resets the volume per request in a middleware (port 8090).
- **Verification without a key**: a throwaway OpenAI-compatible stub (scratchpad only, not in the repo) served via `AICONTROL_E2E_BASE_URL` → both e2e tests passed, proving the harness wiring (server, containers, exporter, example concurrency). This is **not** the real e2e run.
- **To finish**: put `OPENAI_API_KEY=...` in the root `.env`, then `cd sdk && uv run pytest -m e2e` and `cd api && uv run pytest -m e2e`.

**Status**: Completed (real-API e2e runs pending OPENAI_API_KEY)

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| OpenAI instrumentor is tested upstream against `openai` 1.99.7 while we use 3.x | Verified in a spike and by Task 3 tests (sync, stream, async, tools, errors); versions pinned; tests catch upgrade breakage |
| Instrumentor output format keeps evolving (legacy `gen_ai.prompt.N.*` vs JSON `gen_ai.input.messages`) | Parsing isolated in `mapper.py`; other formats added when other providers are |
| `respx` does not intercept `openai` 3.x → tests could hit the real API | Tests inject `httpx.MockTransport` via `http_client=` and use a non-routable `base_url` |
| MinIO community edition in maintenance mode (no new community images) | Local-only stand-in, pinned tag; code uses plain S3 API so AWS S3 / GCS / SeaweedFS drop in via config |
| GCS S3-interoperability differences | Only `put`/`get`/`list` used; add a GCS integration test when that provider is wired in |
| S3 write succeeds, DB insert fails → orphan object | Deterministic key; retry overwrites and inserts; orphans harmless (optional cleanup job later) |
| Many small objects (one per call) | Fine for v1; later compaction job to Parquet per volume/day without SDK or ingest changes |
| Searching inside message content no longer possible in Postgres | Out of scope for v1; later via DuckDB over S3/Parquet or a search index |
| Export of a large volume is slow (many GETs) | Bounded-concurrency fetch; later Parquet compaction |
| Volume lost in threads / background workers | `wrap_context` helper; documented; tests prove fallback |
| Volume grows after an evaluation → scores not reproducible | Export returns a snapshot (call IDs + cutoff) |
| Docker required for Postgres, MinIO and tests | Documented; compose healthchecks give clear errors |
| Short-lived scripts exit before batch is sent | `atexit` flush + public `flush()` |
| HTMX UI outgrown by rich evaluation screens | REST API already exists; a React UI can be added later without backend changes |

## Out of Scope (v1)

- Evaluation engine: evaluation runs, mechanisms, scores, LLM-as-judge / human-as-judge (next plan)
- Parquet compaction / DuckDB analytics over S3
- Full-text search inside message content
- Authentication and `user_id` injection (column reserved)
- Real AWS S3 / GCS wiring and tests (config-ready only)
- Cost computation (tokens are stored to enable it) — separate feature
- OpenAI Responses API
- Providers other than OpenAI Chat Completions (Anthropic, Gemini, native Ollama client, LangChain, ...) and fixing their tool-call capture gaps (e.g. OpenLLMetry's Ollama instrumentor drops reply tool calls)
- Conversation inference / cross-call deduplication
- WebSocket live streaming (UI polls)
- Metrics and logs (traces only)
- TypeScript SDK
