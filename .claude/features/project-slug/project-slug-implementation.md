# Implementation Log: Project slugs

Requested 2026-10-09: when a user creates a project, generate a **slug**; the SDK uses the slug, not the name.

## Decisions

- **Slug generation** (`api/app/slugs.py`): lowercase, accents folded (NFKD → ASCII), every run of characters that are not `a-z0-9` becomes one hyphen, trimmed, at most 64 characters, `project` if nothing is left (for example `日本語`). A taken slug gets `-2`, `-3`… (smallest free number). The slug never changes.
- **One identifier everywhere**: the SDK (`aicontrol.init(project=<slug>)`), the resource attribute `aicontrol.project`, the API addresses (`/api/projects/{slug}/...`), the web addresses (`/projects/<slug>/...`), the S3 keys of new objects (`projects/{slug}/volumes/...`) and `NewCall.project`. The name is a label shown in the UI.
- **The SDK accepts only a slug** and refuses a name at startup with a hint (`'My Project' is not a slug ... Did you mean 'my-project'?`). The API's "project not found" answer and the SDK's one-time log both say that the slug (shown on the project page) is expected, not the name.
- **Names**: still unique (case-sensitive), but any text is allowed now (the `/` restriction existed because the name was an address segment).
- **Race-safe creation**: `repo.create_project` inserts with `ON CONFLICT DO NOTHING` on either unique constraint, then tells a taken name (`ProjectExistsError`) from a slug taken a moment ago (retry with the next number); tests run concurrent creations.
- **Migration** `d41f7a2c9b60_add_project_slug`: adds `projects.slug` (unique, not null) and backfills it from the names with the same rules (copied into the migration so it never changes). Checked on a copy of the real dev database: `default` → `default`, `Test` → `test`, 19 calls kept.

## Files

- API: `app/slugs.py` (new), `app/models.py`, `alembic/versions/2026_10_09_1500-d41f7a2c9b60_add_project_slug.py` (new), `app/repository.py`, `app/schemas.py` (`ProjectOut.slug`, `CallSummary.project` is the slug), `app/routes/read.py`, `app/routes/ingest.py`, `app/ingest/mapper.py`.
- SDK: `_config.py` (`resolve_project` validates a slug), `_project_check.py` (message).
- Web: `api/types.ts`, `components/ProjectsProvider.tsx`, `ProjectSwitcher.tsx`, `NewProjectModal.tsx`, `SdkSnippet.tsx`, `pages/Landing.tsx`, `ProjectPage.tsx`, `ObservePage.tsx`, `lib/projectName.ts`.
- Docs: `README.md` (new "Upgrading to project slugs" section), `web/README.md`, `sdk/README.md`.

## Verification

- API 229 passed, SDK 98 passed, e2e subset (missing project → created) passed against a fake OpenAI with real Postgres and MinIO; ruff clean; web type-check, lint and build clean.
- Browser (Chrome, throwaway stack, real SDK): 24 checks passed: the SDK refuses a name and suggests the slug; the slug of a missing project logs one message; creating "Support Desk" opens `/projects/support-desk` showing the slug and a snippet with it; the real SDK run with the slug then appears in the UI; `support desk` becomes `support-desk-2`; `Sales / EMEA` becomes `sales-emea`; a duplicate name is refused; the switcher shows names with slugs and finds a project by part of its slug; a name in an address is not a project; creating from an unknown address lands on the generated slug; dark mode and phone width.

## Follow-ups

- The dev database must be migrated before the new API runs against it: `cd api && uv run alembic upgrade head`.
- SDK code that still passes a project name must switch to the slug.

## Follow-up (2026-10-10): the slug and the code appear while the name is typed

- The **New project** dialog shows the slug the name will get as it is typed (`web/src/lib/slug.ts` mirrors `api/app/slugs.py`, including the `-2`, `-3` numbering against the existing projects; checked identical to the API on 35 names and 20 numbering cases) and, under it, the code to copy with that slug: `import aicontrol` / `from openai import OpenAI` / `aicontrol.init(project="<slug>")   # once at startup (or set AICONTROL_PROJECT)` / `client = OpenAI()` / `client.responses.create(model="gpt-5-mini", input="What is the capital of France?")`. Nothing is shown while the name is empty.
- The code block was **removed** from the project page (it keeps the one-line "Slug: …" note) and from the start page.
- Browser run (Chrome, real clipboard): 22 checks passed, including the copy button, live updates, the numbering matching the slug the API then generated, and the dialog on a 390px phone.

