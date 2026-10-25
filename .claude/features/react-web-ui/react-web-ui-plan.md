# Feature Plan: React Web UI (`web/` folder)

## Overview

A new top-level `web/` folder holds the whole UI as a React + TypeScript app (built with Vite). It looks
and behaves like today's server-rendered UI: same sidebar, timeline and "Show full input" panel, same CSS.
The API stops serving HTML and becomes a pure JSON and OTLP server. The old Jinja + HTMX UI is removed in
the very last task, only after the React app matches it.

This plan covers only this first restructuring step (the `web/` folder). Other restructuring would be
separate plans.

```
AIControl/
├── api/        FastAPI: OTLP ingest + JSON API (no HTML any more)
├── sdk/
├── examples/
└── web/        React + TypeScript + Vite
    ├── package.json  vite.config.ts  index.html  .env.example  README.md
    └── src/
        ├── main.tsx  App.tsx          router + page shell
        ├── api/        client.ts  types.ts
        ├── components/ Sidebar  ConversationList  CallCard  Message  FullInput
        ├── pages/      Landing  VolumePage
        ├── hooks/      polling and data hooks
        ├── lib/        format.ts (UTC dates)
        └── styles/     app.css  (copied from today's UI)
```

How it is run (two separate servers):

```
terminal 1:  cd api && uv run fastapi run app/main.py --port 8000
terminal 2:  cd web && npm install && npm run dev        →  open http://localhost:5173
```

## Requirements Summary

| Question | Decision |
|---|---|
| Old UI (Jinja + HTMX) | Replace it. It is removed only in the last task, after the React app matches it. |
| Serving | Two separate servers: React on its own port (Vite, 5173), API on 8000 with CORS |
| Sidebar data | New endpoint `GET /api/conversations?limit=` returning `{items, has_more}`. `/api/volumes` stays untouched. |
| Testing | Deferred by decision: no tests are written in this plan, for React or for the API. Verification is type-check, build, lint, the existing suite and manual browser checks. |
| `http://localhost:8000/` after the UI is gone | Redirects to `/docs` |

## Findings from exploration

- Repo root: `api/`, `sdk/`, `examples/`, `docker-compose.yml`, `.env.example`, `README.md`. No JavaScript, no
  Dockerfile and no CI today.
- Node 25.9, npm 11, pnpm, yarn and bun are installed on the dev machine.
- `.gitignore` is Python-only; the existing `dist/` rule already covers a Vite build folder, `node_modules/`
  is missing.
- The API has no CORS configuration. Settings come from `api/app/config.py` (env or the root `.env`).
- The JSON API already covers what the UI shows: calls of a volume with cursor paging
  (`GET /api/volumes/{name}/calls`), one call with its full trace (`GET /api/calls/{id}`), the export. The
  one gap: `GET /api/volumes` returns all volumes as a bare list, with no limit and no "has more", while the
  sidebar needs "latest 30, load more". `repo.list_recent_volumes(session, limit)` already exists for it.
- The UI to reproduce: the sidebar (Monitoring, latest 30, Load more, 5s refresh only while open, current
  highlight, "N calls · Oct 4, 10:35" with UTC tooltip), the landing page, the timeline (call cards, tags,
  new messages and tool calls, cursor Load more, 2s refresh, From/To filters, empty and 404 states), the
  "Show full input" panel (input and output messages, tool definitions, all attributes, S3 key, missing
  trace error), dark mode and the narrow layout.
- Volume names may contain `/` (for example `team/support`), so URLs must encode them.

## Architecture Decisions

Defaults I chose (to be reviewed at approval):

1. **`web/` sits at the repo root** next to `api/` and `sdk/`.
2. **Vite + React + TypeScript.** The API shapes are typed in `web/src/api/types.ts`, mirroring
   `api/app/schemas.py`.
3. **npm** as the package manager (it ships with Node).
4. **React Router, hand-written data hooks, no data-fetching library.** The sidebar and timeline need a few
   timers; the hooks mirror the logic that exists today. The conversation route is a wildcard
   (`/volumes/*`) so names with slashes work.
5. **Same CSS, no UI library.** `app.css` is copied over, so the look is unchanged, dark mode included.
6. **Same behavior as today:** latest 30 conversations with Load more (+30, capped at 500); refresh every 5s
   only while Monitoring is open (nothing is requested while collapsed); timeline refresh every 2s using the
   cursor; From/To filters in the URL; dates in UTC.
7. **Sidebar state survives navigation** (no full page reload), so the open state and loaded conversations
   are kept when clicking a conversation.
8. **Configuration:** the web app reads `VITE_API_URL` (default `http://localhost:8000`); the API reads
   `CORS_ORIGINS`, a JSON list defaulting to `http://localhost:5173` and `http://127.0.0.1:5173`, allows
   only `GET`, no credentials.
9. **Housekeeping:** `.gitignore` gets `node_modules/`.

## Implementation Tasks

### Task 1: API additions: `/api/conversations` and CORS

Additive: nothing existing changes.

**Files to modify/create**:
- `api/app/routes/read.py` - `GET /api/conversations`
- `api/app/schemas.py` - `ConversationPageOut(items: list[VolumeOut], has_more: bool)`
- `api/app/config.py` - `cors_origins` setting
- `api/app/main.py` - add `CORSMiddleware` (settings are needed at app creation, not only in the lifespan)
- `.env.example` - document `CORS_ORIGINS`

**Implementation**:
1. `GET /api/conversations?limit=30` (`ge=1`, `le=500`, default 30) calls `repo.list_recent_volumes` and
   returns `{items, has_more}`, reusing `VolumeOut`.
2. Add `CORSMiddleware` with `allow_origins` from `cors_origins`, `allow_methods=["GET"]`, no credentials.
3. Document the endpoint through its docstring so it shows in `/docs`.

**Tests**: none (deferred by decision).

**Verification**:
- [x] The existing suite (`uv run pytest -q` in `api/`) still passes and `ruff` is clean (143 passed, ruff clean)
- [x] `curl '.../api/conversations?limit=2'` returns two items and `has_more` (also: default 30, `limit=40` gives 40 items and `has_more=false`, `limit=0` and `501` give 422)
- [x] `curl -H 'Origin: http://localhost:5173' -i .../api/volumes` includes `access-control-allow-origin` (also a preflight)

**Acceptance criteria**:
- [x] The endpoint answers with the right shape and limits
- [x] `/api/volumes` and every other existing endpoint behave exactly as before
- [x] An origin outside the list gets no allow-origin header

**Status**: Completed

**Completion Notes**:
- **Files modified**: `api/app/routes/read.py` (`GET /api/conversations`), `api/app/schemas.py` (`ConversationPageOut`), `api/app/config.py` (`cors_origins`), `api/app/main.py` (CORS middleware; `config` is now read once at the top of `create_app` instead of inside the lifespan), `.env.example` (`CORS_ORIGINS`, commented out).
- **Key decisions**: CORS allows only `GET`, no credentials, and only the listed origins. A request from another origin still gets its normal response but without `access-control-allow-origin`, so the browser blocks it. The SDK's `POST /v1/traces` is unaffected (not a browser call).
- **Verification setup reused for the following tasks**: a throwaway Postgres container `aicontrol-ui-check` (port 5543, 40 seeded conversations) and the app on `http://127.0.0.1:8011` with an in-memory trace store, started with `spike/launch_ui_check.py` from the monitoring-sidebar feature. The dev database and MinIO are never touched.
- **Notes for next task**: the API on 8011 serves both the old UI and the new JSON API until Task 7. Restart it after any API change (the app does not reload).

**Files to modify/create**:
- `web/` - Vite React-TS project: `package.json`, `vite.config.ts`, `tsconfig*.json`, `index.html`, lint config, `.env.example`, `README.md`
- `web/src/main.tsx`, `App.tsx` - router and page shell (sidebar frame + content)
- `web/src/api/client.ts`, `types.ts` - typed fetch client reading `VITE_API_URL`, with errors surfaced
- `web/src/lib/format.ts` - UTC date formatting (`Oct 4, 10:35`, `2026-10-04 10:35:00`)
- `web/src/pages/Landing.tsx`
- `web/src/styles/app.css` - copied from `api/app/ui/static/app.css`
- `.gitignore` - add `node_modules/`

**Implementation**:
1. Create the project and scripts (`dev`, `build`, `preview`, `lint`).
2. Routes: `/` (landing) and `/volumes/*` (conversation, placeholder until Task 4).
3. Landing: heading, "Click Monitoring to browse your conversations.", the SDK snippet.
4. Types for `VolumeOut`, `ConversationPage`, `CallSummary`, `CallPage`, `CallDetail` and the trace.

**Tests**: none (deferred by decision).

**Verification**:
- [x] `npm run build` (includes the type-check) and `npm run lint` pass
- [x] `npm run dev` shows the landing page at `http://localhost:5173`, the same as the old home page (every element box within 1px of the old page in real Chrome)

**Acceptance criteria**:
- [x] The app builds and runs
- [x] The client reaches the API across the two origins (CORS works): the app's own client, run in the page at 5173, got `/api/conversations` from 8011, and a 404 became an `ApiError` carrying the API's message

**Status**: Completed

**Completion Notes**:
- **Files created/modified**: `web/` (`package.json`, `package-lock.json`, `index.html`, `vite.config.ts`, `tsconfig*.json`, `.oxlintrc.json`, `.env.example`, `README.md`, `src/env.d.ts`, `src/main.tsx`, `src/App.tsx`, `src/api/{types,client}.ts`, `src/lib/format.ts`, `src/hooks/{useTitle,useCurrentVolume}.ts`, `src/components/{Layout,Sidebar}.tsx`, `src/pages/{Landing,NotFound,VolumePage}.tsx`, `src/styles/app.css` copied from `api/app/ui/static/app.css`), and the root `.gitignore` (`node_modules/`).
- **Versions** (what `npm create vite@latest` and npm gave today): Vite 8.3, React 19.2, TypeScript 6.0, oxlint as the linter (the template no longer ships ESLint), `react-router` 8.4. React Router 8 needs Node >= 22.22; this is in `engines` and the README. `BrowserRouter`, `Routes`, `Route`, `Outlet`, `Link`, `useMatch`, `useSearchParams` and `useParams` are still exported in v8.
- **Key decisions**: wildcard route `volumes/*`; `useCurrentVolume` uses `useMatch('/volumes/*')`, which decodes `%2F`, so both `team%2Fsupport` and `team/support` give `team/support`. The sidebar is never remounted, so its open state survives navigation. `ApiError.status` is 0 when the API cannot be reached. `erasableSyntaxOnly` is on, so no TypeScript enums or constructor parameter properties. `<link rel="icon" href="data:,">` avoids a favicon request. Dev and preview ports are fixed (5173, 4173) because the API's default CORS origin is 5173.
- **Patterns established**: all API access goes through `api` in `src/api/client.ts`; all times go through `src/lib/format.ts` (UTC); one global stylesheet, no CSS modules; page titles via `useTitle`.
- **Verification setup**: start the dev server with `VITE_API_URL=http://127.0.0.1:8011 npm run dev` to use the throwaway API (the default points at 8000). The Chrome check is `verify/task2_check.js` (needs `puppeteer-core`).
- **Harness gotcha**: opening a second headless tab sends the first one to the background, where clicks can hang; close the extra tab (done in the script).
- **Notes for next task**: `Sidebar.tsx`'s `<details>` has an empty body. Put `ConversationList` inside it and render it only while `open` is true, so nothing is requested while collapsed. `VolumePage.tsx` is a placeholder until Task 4.

### Task 3: Sidebar conversation list

**Files to modify/create**:
- `web/src/components/Sidebar.tsx`, `ConversationList.tsx`
- `web/src/hooks/` - polling hook

**Implementation**:
1. Monitoring toggle, initially open when the page loads on a conversation.
2. Fetch `/api/conversations?limit=N`; show name (truncated with ellipsis, full name in the tooltip) and
   "N calls · Oct 4, 10:35" (tooltip: full UTC time); highlight the current conversation.
3. Load more raises `limit` by 30 (cap 500); at the cap show "Showing the latest N conversations."
4. Refresh every 5s only while open; nothing is requested while collapsed.
5. Empty state: "No conversations yet…".

**Tests**: none (deferred by decision).

**Verification**:
- [x] Type-check, build and lint pass
- [x] In the browser: nothing requested while collapsed, list loads on open, Load more with 31+ conversations, a new conversation appears by itself, `team/support` works (25 checks in real Chrome, `verify/task3_check.js`)

**Acceptance criteria**:
- [x] Behaves like the old sidebar (the first 30 names and subtitles are identical to the old UI's list, checked in the browser)
- [x] Sidebar state survives navigating between conversations (no page reload; the loaded list of 40 is kept)

**Status**: Completed

**Completion Notes**:
- **Files created/modified**: `web/src/hooks/useLive.ts` (new), `web/src/components/ConversationList.tsx` (new), `web/src/components/Sidebar.tsx` (renders the list), `web/src/styles/app.css` (+ `.conversations .error-text`).
- **Key decisions**: `ConversationList` is always mounted inside the `<details>` and is enabled only while it is open, so data and the Load more `limit` survive a collapse and nothing is requested while collapsed. Load more raises `limit` by 30 (cap 500) and the whole list is re-requested, as in the old UI; at the cap a note replaces the button. A failed first load shows "Could not load conversations: …"; a failed refresh keeps the list and adds "Refresh failed: …"; it recovers by itself on the next tick.
- **Patterns established**: `useLive(load, intervalMs, enabled)` is the hook for "fetch now and every N seconds while enabled" (aborts the call in flight when `load` or `enabled` changes, skips a tick while a call is running, keeps the last data). `load` must be a stable callback (`useCallback`). Links use `` `/volumes/${encodeURIComponent(name)}` ``.
- **Verified in Chrome (25 checks)**: collapsed 6.5s = 0 requests; opening = 1 request and 30 items, newest first, `1 call · Oct 4, 09:39`; refresh while open; collapse = 0 requests; re-open refreshes at once; Load more = `limit=60`, 40 items, no duplicates; the slash link is `/volumes/team%2Fsupport`; navigating keeps the page (a marker on `window` survived) and the 40 loaded items; a new conversation appeared at the top after 3.4s; empty, error, refresh-failure and recovery states (requests intercepted); narrow layout; dark and live screenshots.
- **Harness notes**: `verify/task3_check.js` needs freshly seeded data (`verify/reset_data.sh` truncates the throwaway database and re-seeds the 40 conversations); the live conversation name is unique per run. The old UI's `/favicon.ico` 404 is excluded.
- **Notes for next task (Task 4)**: `VolumePage.tsx` is a placeholder; `api.calls(volume, {from, to, limit, cursor}, signal)` is ready. The timeline appends pages by cursor, so it needs its own hook (not `useLive`, which replaces its data). Seed richer data for the browser check (tool calls, an error call, 100+ calls for Load more, a hostile name) and compare the cards' text with the old UI's.

### Task 4: Conversation timeline

**Files to modify/create**:
- `web/src/pages/VolumePage.tsx`, `web/src/components/CallCard.tsx`, `Message.tsx`
- `web/src/hooks/` - calls hook (cursor paging + live refresh)

**Implementation**:
1. Fetch `/api/volumes/{name}/calls` (name encoded with `encodeURIComponent`); cards show time, model,
   `in → out tok`, cached/reasoning/stream/finish/tools tags, latency and status.
2. Show each call's new messages with roles, tool call badges and tool call ids; errors are highlighted.
3. Load more by cursor; once there is no more, refresh every 2s for calls after the last cursor.
4. From/To filters kept in the URL query; "Clear" link.
5. Empty ("No calls yet…" / "…in this time range"), unknown conversation (404) and error states.
6. Message text is rendered as text only (no raw HTML).

**Tests**: none (deferred by decision).

**Verification**:
- [x] Type-check, build and lint pass (lint has no warnings)
- [x] In the browser: a live call appears in the timeline by itself; filters narrow results; a hostile message such as `<script>…` is shown as text (28 checks in real Chrome, `verify/task4_check.js`). The live call was an SDK-instrumented call with a mocked OpenAI reply posted to the real ingest endpoint, not `examples/openai_chat.py` (which needs a real key).

**Acceptance criteria**:
- [x] Behaves like the old timeline: for four conversations (tool calls, an error call, 50 calls, hostile text) every card has the same text, CSS classes, message roles and id as in the old UI. The only intended difference is the "Show full input" button, which Task 5 adds.

**Status**: Completed

**Completion Notes**:
- **Files created/modified**: `web/src/hooks/useCalls.ts`, `web/src/components/Message.tsx`, `web/src/components/CallCard.tsx` (new); `web/src/pages/VolumePage.tsx` (the placeholder is replaced).
- **Key decisions**:
  - `useCalls` keeps a `key` (`volume|from|to|attempt`) inside its state and derives "loading" while rendering when the key changes, so no state is reset inside an effect. oxlint's `react/set-state-in-effect` warning on my first version was right, and the rewrite is warning-free.
  - It loads 50 calls per page; once everything is loaded (`hasMore` false) it asks for new calls every 2s after the last cursor. While "Load more" is pending it does not poll (verified: 0 requests in 4.5s).
  - Errors: first load fails gives "Could not load the calls: …" and a Retry button; a failing Load more or refresh keeps the calls and adds "Refresh failed: …", cleared by the next success; a 404 gives "Conversation “x” not found.".
  - The filter lives in the URL (`?from=&to=`). The browser normalises a `datetime-local` value such as `10:01:00` to `10:01`, so URLs and inputs show the short form. The form is remounted (`key`) when the conversation or filter changes so the inputs get the new defaults.
  - The "Load more" `<li class="more">` sits inside `<ol class="timeline">` like the old markup.
- **Patterns established**: `CallCard`/`Message` mirror the old templates line by line (tags, titles, texts); message text is rendered as text only, with no raw HTML anywhere. `compactJson` (in `lib/format.ts`) reproduces Python's `{"city": "Paris"}` spacing.
- **Verified in Chrome (28 checks)**: cards identical to the old UI for `tools-demo`, `error-demo`, `timeline-long` (first 50) and the hostile conversation; tool call badge and tool result card; error card highlighted; hostile name and text shown literally (no injected elements, no alert); Load more 50 to 100 to 120 with unique ids and the button gone; refresh requests every ~2s with a cursor once everything is loaded; a posted call appended by itself and the sidebar showing 121 calls; From inclusive and To exclusive; filter in the URL, Clear; empty range message; unknown conversation; clicking another conversation swaps the timeline without a reload; Retry, refresh-failure note and its recovery; narrow layout; dark and light screenshots.
- **Harness notes**: the old template renders `class="call "` with a trailing space, so classes are compared trimmed; CSS uppercases role labels, so text checks are case-insensitive; the check resets and re-seeds its own data (`verify/seed_timeline.py`, `verify/post_demo_spans.py`).
- **Notes for next task (Task 5)**: add the "Show full input" button and a `<div className="full">` to `CallCard`; `api.call(id)` and the `Trace`/`CallDetail` types exist. The old panel also shows the S3 key, which `CallDetail` does not return yet, so add `trace_key` to `CallDetail` in the API (additive) and then restart the API on 8011, because the app does not reload. The Task 4 comparison strips "Show full input" from the old cards; after Task 5 that is no longer needed.

### Task 5: "Show full input" panel

**Files to modify/create**:
- `web/src/components/FullInput.tsx`

**Implementation**:
1. On click, fetch `/api/calls/{id}`; show input messages, output messages, tool definitions and all
   attributes (collapsible), and the S3 key.
2. When the trace object is missing (`trace_error`), show "Trace object … not found in storage".

**Tests**: none (deferred by decision).

**Verification**:
- [x] Type-check, build and lint pass
- [x] In the browser: a call with tools, a call without, a call whose trace object is missing, and a trace with hostile text (17 checks in real Chrome, `verify/task5_check.js`)

**Acceptance criteria**:
- [x] Behaves like the old panel: for the 6 calls tried (tool definitions + tool call/result, an error call, a hostile trace, a missing trace object), the text a reader sees in the panel, with the collapsed sections opened, is identical to the old UI's, including the S3 key.

**Status**: Completed

**Completion Notes**:
- **Files created/modified**: `web/src/components/FullInput.tsx` (new), `web/src/components/CallCard.tsx` (button and panel), `web/src/api/types.ts` (`trace_key` on `CallDetail`), `web/src/styles/app.css` (`.trace-key code { word-break: break-all; }`), and in the API `api/app/schemas.py` and `api/app/routes/read.py` (`CallDetail.trace_key`).
- **Deviation from the plan (API, additive)**: `GET /api/calls/{id}` did not return the S3 key, which the old panel shows, so `CallDetail` now has a `trace_key` field (in the normal and the "trace object missing" responses). Nothing else about the endpoint changed; the API suite still passes (143).
- **Key decisions**: the button toggles between "Show full input" and "Hide full input" (the old button always said "Show full input" and re-fetched on each click). The panel is fetched when it is opened and aborted if the card goes away. An open panel stays open across the 2s refresh polls (the cards keep their keys). Fetch failure gives "Could not load the full input: …"; a missing trace object shows the API's `trace_error` text.
- **CSS improvement over the old UI**: a long S3 key made the page scroll horizontally on a 600px window. The old UI does exactly the same (measured: page width 644 against 600 in both), so this is a pre-existing quirk; the new stylesheet wraps the key.
- **Verified in Chrome (17 checks)**: panels identical to the old UI's for tools-demo, error-demo, hostile-trace and a missing-trace call; headings, the two collapsible sections (collapsed at first), roles, S3 key format, indented JSON; hide and show; the open panel survives 5s of refresh polls; hostile system and user text in a stored trace is shown literally (no injected element, no alert); API failure message and recovery; light, dark and narrow screenshots.
- **Harness notes**: panels are compared with `innerText` after opening every `<details>`, because the old Jinja output has whitespace between elements and React has none (a raw `textContent` comparison reported false differences). After an API code change the throwaway API on 8011 must be restarted, and its in-memory trace store is then empty, so the check re-posts its demo spans (`verify/post_demo_spans.py`, now also creating `hostile-trace`).
- **Notes for next task (Task 6)**: the app is feature-complete. Remaining differences from the old UI that are intentional: "Hide full input" label, the sidebar keeping its state across navigation, "Refresh failed" notes, and the wrapped S3 key. Run the production build (`npm run build` then `npm run preview` on 4173, with `VITE_API_URL` set at build time) and compare once more side by side.

### Task 6: Parity check against the old UI

**Implementation**:
1. Run the old UI (8000) and the new one (5173) on the same data, side by side.
2. Check: dark mode, the narrow layout (under 720px), a hostile name (`<script>…`), a long name, a slash
   name, 31+ conversations, a live chat, the production build (`npm run build` + `npm run preview`).
3. List what was compared and any difference found.

**Tests**: none (deferred by decision).

**Acceptance criteria**:
- [x] Nothing visibly missing compared with the old UI
- [x] Differences, if any, are written down and accepted (see the list below)

**Status**: Completed

**Completion Notes**:
- **What was compared** (all in real Chrome, old UI on 8011 against the React UI, same data):
  - **Pixels:** 18 screens, each rendered by both UIs and compared pixel by pixel (`verify/task6_parity.js`): landing, tool calls, tool calls with the full input open, an error call, the first 50 of a long conversation, hostile name and text, hostile text inside the full input, an edge-case conversation (unknown model, `? → ?` tokens, `stream` tag, `0 ms`, two finish reasons, `1 tool` and `3 tools`, error type, multi-line text, an empty assistant message, a tool call with nested arguments and `café ☕`), a long conversation name, the slash name `team/support`, a missing trace object in the full input, the sidebar scrolled to Load more, a time filter, an empty time range, dark landing, dark full input, a 600px window and a 600px window with the full input. **Result: 18 of 18 identical, on both the dev server (5173) and the production build served by `vite preview` (4173), with no console or network errors.**
  - **Behaviour:** the Task 3, 4 and 5 suites (25, 28 and 17 checks) re-run on the final code, all pass.
- **Differences accepted (intended)**:
  1. The full-input button reads "Hide full input" while open (the old one always said "Show full input"). The pixel run puts the old label back on the new button first, so it measures everything else.
  2. Navigating between conversations no longer reloads the page: the sidebar keeps its open state and the conversations already loaded.
  3. Failures are shown ("Could not load…", "Refresh failed: …", with Retry on the timeline); the old UI stayed silent on a failed refresh. There are also "Loading…" states.
  4. An unknown conversation shows a friendly message instead of the old UI's raw JSON 404.
  5. The S3 key wraps on narrow windows (the old UI overflowed sideways: measured 644px page width at 600px in both before the fix). It is below the first screen, so the pixel run does not show it.
- **Found and fixed during the gate**:
  - Sub-pixel differences (9 to 465 pixels per screen) came from React splitting labels such as `{latency} ms` into several text nodes while the old template emitted one. Building each label as one string made the screens identical, which also confirmed the cause.
  - **The production preview was blocked by CORS**: the API only allowed port 5173 while the README documents `npm run preview` on 4173. The UI showed "Cannot reach the API at …" (a graceful failure) but did not work. The API's default `cors_origins` now also contains `http://localhost:4173` and `http://127.0.0.1:4173`; `.env.example` and `web/README.md` are updated. **Deviation from architecture decision 8** (the default list was only the 5173 origins).
- **Not covered**: only Chrome; small data sets; no real OpenAI conversation; the pixel run compares the first viewport of each screen, not whole pages; no automated tests (deferred by decision). Two old-UI quirks are not reproduced on purpose: a message with a missing role shows `None` in the old UI and `unknown` in the new one (no such data was seen), and the old UI's `/favicon.ico` 404.
- **Notes for next task (Task 7)**: the throwaway API on 8011 and the dev and preview servers are still running; stop them at the end. `api/app/ui/` and `api/tests/integration/test_ui.py` are the code and tests to delete. After the old UI is gone, the pixel comparison can no longer be re-run (it needs the old UI), so its logs (`verify/task6_parity_*.log`) are the record.

### Task 7: Remove the old UI, redirect `/`, update docs

**Files to modify/create**:
- `api/app/ui/` - delete (routes, templates, static)
- `api/tests/integration/test_ui.py` - delete (the 32 tests of the old UI)
- `api/app/main.py` - remove the UI router and the static mount; add `/` → redirect to `/docs`
- `api/pyproject.toml` - drop "and web UI" from the description
- `README.md` - structure, quickstart with the two terminals, the new endpoint in the REST table, a Web UI section describing the React app

**Implementation**:
1. Remove the old UI code and its tests; keep `app/views.py` (still used by the ingest mapper and the export).
2. `GET /` redirects to `/docs`.
3. Update the README.

**Tests**: none new. The deleted tests are the old UI's own.

**Verification**:
- [x] `uv run pytest -q` and `ruff` pass in `api/` (111 passed, which is 143 minus the 32 deleted UI cases; ruff clean)
- [x] `GET /` redirects to `/docs` (HTTP 307, and the redirect leads to the docs page with HTTP 200)
- [x] The React app still works end to end against the API (sidebar 24, timeline 24 and full input 13 checks on the dev server, timeline and full input again on the production build, all passing without the old UI)

**Acceptance criteria**:
- [x] No HTML is served by the API any more: `/static/app.css`, `/ui/conversations` and `/volumes/<name>` return 404; `/docs` and `/openapi.json` (generated pages) remain
- [x] The README describes the two-terminal workflow

**Status**: Completed

**Completion Notes**:
- **Files deleted**: `api/app/ui/` (10 files: the routes, `static/app.css` and 6 templates) and `api/tests/integration/test_ui.py` (29 test functions, 32 cases).
- **Files modified**: `api/app/main.py` (UI router and static mount removed, `GET /` redirects to `/docs` and is hidden from the schema), `api/pyproject.toml` (description), `README.md` (intro with `web/`, diagram, a five-step quickstart with a second terminal for the web UI, `GET /api/conversations` and `trace_key` in the REST table, a rewritten Web UI section, Node in the requirements, web commands under Development, and a line saying the web UI has no automated tests yet), `.claude/features/monitoring-sidebar/monitoring-sidebar-plan.md` (a "superseded" note, since that plan's code no longer exists).
- **Left alone on purpose**: `api/app/views.py` (still used by the ingest mapper and the export), `repo.list_volumes` (still used by `GET /api/volumes`), and `jinja2`, which is no longer used by our code but comes with `fastapi[standard]` (nothing to remove from `pyproject.toml`).
- **Verification scripts after the removal**: the Task 3, 4 and 5 scripts take `NO_OLD=1` (skip the comparisons with the old UI) and `NEW=<address>`. The Task 6 pixel comparison needs the old UI and can no longer be re-run; its logs (`verify/task6_parity_dev.log`, `verify/task6_parity_prod.log`) are the record.
- **What you need to do**: restart the API you started on port 8000. That process (started 14:22) still holds the old code in memory, and since the templates are gone `GET /` on it now returns HTTP 500. Then start the UI with `cd web && npm install && npm run dev` and open `http://localhost:5173`.
- **Your own data**: the dev database was never written to by these checks (all used a throwaway Postgres container, now removed). Its `bob-chat-7` volume came from your own live test (4 calls from `openai-chat-example`, created right after your server restart).

## Risks and Mitigations

- **Coverage drops:** Task 7 deletes the 32 tests that cover today's UI and the React app has no automated
  tests (deferred by decision), so regressions are only caught by hand. Mitigation: Task 6 is a deliberate
  side-by-side gate before anything is deleted, and it records what was compared.
- **Old browser-check scripts stop applying:** the Puppeteer scripts in
  `.claude/features/monitoring-sidebar/spike/` use the old UI's HTML. They stay as history.
- **Slash names:** `team/support` must survive the router and the API URL. Mitigation: wildcard route,
  `encodeURIComponent` for API calls, manual check in Task 3.
- **CORS or port mismatch:** shows up as a console error in the browser. Mitigation: sensible defaults and
  the `CORS_ORIGINS` setting.
- **Dates:** the old UI formats UTC on the server. Mitigation: one shared formatting function.
- **Two servers to start:** documented in the README and `web/README.md`.

## Out of Scope

- Automated tests for React or for the new endpoint (deferred by decision)
- Playwright and CI
- Docker or an nginx service for the web app
- Serving the build from FastAPI
- A data-fetching library, a UI library or Tailwind
- Generating TypeScript types from the OpenAPI schema
- New features such as search, and other restructuring steps
