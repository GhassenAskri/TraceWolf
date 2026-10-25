# Implementation Log: React Web UI

Plan: react-web-ui-plan.md

Execution note: the user asked to implement all tasks in one go, so the "stop after each task" gate was
skipped. Tasks were still done strictly one after another, each verified and logged before the next.

## Task 1: API additions: `/api/conversations` and CORS — Completed 2026-10-04

- **Files created/modified**:
  - `api/app/routes/read.py` — `GET /api/conversations?limit=` (1–500, default 30) using `repo.list_recent_volumes`
  - `api/app/schemas.py` — `ConversationPageOut(items, has_more)`
  - `api/app/config.py` — `cors_origins` (default `http://localhost:5173`, `http://127.0.0.1:5173`)
  - `api/app/main.py` — `CORSMiddleware` (GET only); settings read once at app creation
  - `.env.example` — documented `CORS_ORIGINS`
- **Commands to verify** (from `api/`): `uv run pytest -q`; `uv run ruff check . && uv run ruff format --check .`; then `curl` against the app on a throwaway database (see the plan's completion notes).
- **Test results**: existing suite 143 passed, 0 failed, 2 deselected (e2e). Ruff clean. No new tests (deferred by decision). curl checks: all as expected (shape, `has_more`, 422 for limits 0 and 501, CORS headers only for the allowed origin, preflight OK, `/api/volumes` still a bare list, `POST /v1/traces` unaffected).
- **Deviations from plan**: none.
- **Open issues / follow-ups**: none.

## Task 2: Scaffold `web/`, API client, app shell and landing — Completed 2026-10-04

- **Files created/modified**: the whole `web/` project (see the plan's completion notes), root `.gitignore`.
- **Commands to verify** (from `web/`): `npm install`; `npm run build`; `npm run lint`; `VITE_API_URL=http://127.0.0.1:8011 npm run dev`; Chrome check `node ../.claude/features/react-web-ui/verify/task2_check.js`.
- **Test results**: build and type-check pass, lint exit code 0. Chrome: 10 of 11 checks pass; the 11th (no console errors) trips on the 404 that the script provokes on purpose with a conversation that does not exist, and a separate run that only visits the four routes showed no failing request and no console error. The 10 passing checks cover (title, landing text, sidebar collapsed, element boxes within 1px of the old landing page, cross-origin client call, ApiError on 404, `/volumes/team%2Fsupport` and `/volumes/team/support`, unknown route, sidebar state across client-side navigation). The only console error in the full run is the 404 my own check provokes; visiting the four routes alone produced no failing request and no console error. No automated tests (deferred by decision).
- **Deviations from plan**: none in scope. Tooling is newer than assumed (Vite 8, TypeScript 6, oxlint instead of ESLint, React Router 8 needing Node >= 22.22); recorded in `engines` and the README.
- **Issues met along the way**:
  - The first full Chrome run crashed with "Target closed" and the second hung. Cause: the extra tab opened for the old-UI comparison pushed the main tab to the background, where clicks hang. The same sequence passed on its own, and the full script passed after closing the extra tab. A harness problem, not an app problem.
  - A background run I killed myself later produced a "failed, exit 144" notification; that was my own `pkill`.
- **Open issues / follow-ups**: none.

## Task 3: Sidebar conversation list — Completed 2026-10-04

- **Files created/modified**: `web/src/hooks/useLive.ts`, `web/src/components/ConversationList.tsx`, `web/src/components/Sidebar.tsx`, `web/src/styles/app.css`; scripts `verify/task3_check.js`, `verify/post_span.py`, `verify/reset_data.sh`.
- **Commands to verify** (from `web/`): `npm run build`; `npm run lint`; with the throwaway API on 8011 (data reset first): `bash ../.claude/features/react-web-ui/verify/reset_data.sh && node ../.claude/features/react-web-ui/verify/task3_check.js`.
- **Test results**: build and lint pass. Chrome: 25 of 25 checks passed on the final run. No automated tests (deferred by decision).
- **Deviations from plan**: none in scope. Added a visible "Refresh failed" note and automatic recovery, which the old UI did not have (its refresh simply stayed silent).
- **Issues met along the way** (all harness, none in the app):
  - A first run crashed in my own cleanup (request interception switched off while the handler was still attached).
  - A re-run failed on data assumptions because the previous run had added conversations; fixed by resetting the throwaway data before each run and by giving the live conversation a unique name per run.
  - The last failing check was a 404 for `http://127.0.0.1:8011/favicon.ico`, the old UI's missing favicon (found by logging the failing URL), now excluded.
- **Open issues / follow-ups**: none.

## Task 4: Conversation timeline — Completed 2026-10-04

- **Files created/modified**: `web/src/hooks/useCalls.ts`, `web/src/components/Message.tsx`, `web/src/components/CallCard.tsx`, `web/src/pages/VolumePage.tsx`; scripts `verify/task4_check.js`, `verify/seed_timeline.py`, `verify/post_demo_spans.py`.
- **Commands to verify** (from `web/`, with the throwaway API on 8011 and the dev server on 5173 started with `VITE_API_URL=http://127.0.0.1:8011`): `npm run build`; `npm run lint`; `node ../.claude/features/react-web-ui/verify/task4_check.js` (it resets and re-seeds the data itself).
- **Test results**: build passes, lint has no warnings. Chrome: 28 of 28 checks passed on the final run (an earlier note said 31, which was a miscount, corrected after counting the log). No automated tests (deferred by decision).
- **Deviations from plan**: the live-call check used an SDK-instrumented call with a mocked OpenAI reply, not `examples/openai_chat.py` (needs a real key). The "Show full input" button is deliberately absent until Task 5.
- **Issues met along the way**:
  - `oxlint` warned `react/set-state-in-effect` on my first `useCalls`, which reset state inside an effect. I rewrote it to keep a key with the state and derive the loading state during render.
  - The first run of the check had 7 failures, all wrong assumptions in the script: the old template's `class="call "` has a trailing space; CSS uppercases role labels; the browser normalises `datetime-local` values (`10:01:00` becomes `10:01`); and the deliberate unknown-conversation request is a legitimate 404. The app was unchanged between the two runs.
- **Open issues / follow-ups**: none.

## Task 5: "Show full input" panel — Completed 2026-10-04

- **Files created/modified**: `web/src/components/FullInput.tsx` (new), `web/src/components/CallCard.tsx`, `web/src/api/types.ts`, `web/src/styles/app.css`; API: `api/app/schemas.py`, `api/app/routes/read.py`; scripts `verify/task5_check.js`, `verify/task5_narrow.js`, `verify/post_demo_spans.py` (extended).
- **Commands to verify**: API (from `api/`): `uv run pytest -q`; `uv run ruff check . && uv run ruff format --check .`. Web (from `web/`): `npm run build`; `npm run lint`. Browser, with the throwaway API on 8011 restarted on the new code and the dev server on 5173: `node ../.claude/features/react-web-ui/verify/task5_check.js`.
- **Test results**: API suite 143 passed, ruff clean. Web build passes, lint has no warnings. Chrome: 17 of 17 checks passed on the final run. No automated tests (deferred by decision).
- **Deviations from plan**: the API gained an additive `trace_key` field on `CallDetail` (the old panel showed the S3 key and the API did not return it). A one-line CSS fix wraps the S3 key; the old UI had the same overflow on narrow screens.
- **Issues met along the way**:
  - First run: 3 comparisons and the narrow check failed. The comparisons used raw `textContent`, and the old Jinja output has whitespace between elements that React does not emit, so words ran together; switching to `innerText` with the collapsed sections opened fixed it. The narrow failure was real but pre-existing: measured with `verify/task5_narrow.js`, the old UI and the new one both overflowed to 644px at 600px because of the long S3 key.
  - Restarting the API empties its in-memory trace store, so the check re-posts its demo spans every time.
- **Open issues / follow-ups**: none.

## Task 6: Parity check against the old UI — Completed 2026-10-04

- **Files created/modified**: scripts in `verify/` (`task6_parity.js`, `preview_cors.js`, `edge_text.js`, updated `seed_timeline.py` and `task3_check.js`) and logs `verify/task6_parity_dev.log`, `verify/task6_parity_prod.log`. Code changes made because of the gate: label text nodes in `web/src/components/{CallCard,Message,ConversationList,FullInput}.tsx` and `web/src/pages/VolumePage.tsx`; `api/app/config.py` (`cors_origins` + preview origins), `.env.example`, `web/README.md`.
- **Commands to verify**: dev server on 5173 (with `VITE_API_URL=http://127.0.0.1:8011`) and the old UI on 8011; `node ../.claude/features/react-web-ui/verify/task6_parity.js`. Production build: `VITE_API_URL=http://127.0.0.1:8011 npm run build && npm run preview`, then `NEW=http://localhost:4173 node ../.claude/features/react-web-ui/verify/task6_parity.js`.
- **Test results**: pixel comparison 18 of 18 screens identical on the dev server and on the production build, no console or network errors. Behaviour suites on the final code: sidebar 25, timeline 28, full input 17, all passing. API suite 143 passed, ruff clean; web build and lint clean.
- **Deviations from plan**: the API's default CORS list gained the `vite preview` origins (4173); the plan listed only 5173. Reason: the production preview was blocked by CORS (found by the gate, reproduced in Chrome before the fix).
- **Issues met along the way**:
  - First pixel run: 7 screens differed by 9 to 465 pixels. Cause: React's multiple text nodes per label against the old single node. Fixed by building each label as one string; confirmed by the diff dropping to zero.
  - The helper that opens a panel waited for the full trace, which a missing-trace panel does not have; the empty-range page has no call cards. Both were script problems.
  - `pixelmatch`/`pngjs` needed a `Buffer` from puppeteer's `Uint8Array` screenshots.
  - **Two numbers I had written down earlier were wrong and are corrected in the plan and in this log**: Task 4 has 28 checks (I had written 31), and Task 2 was 10 of 11 passing, with the 11th failing on my own deliberate 404 (I had written "11, all pass"). Found by counting the saved logs.
  - The Task 3 script did not reset its own data and failed once on leftovers from another run; it now resets its data like the others.
- **Open issues / follow-ups**: none.

## Task 7: Remove the old UI, redirect `/`, update docs — Completed 2026-10-04

- **Files created/modified/deleted**: deleted `api/app/ui/` and `api/tests/integration/test_ui.py`; modified `api/app/main.py`, `api/pyproject.toml`, `README.md`, `.claude/features/monitoring-sidebar/monitoring-sidebar-plan.md` (superseded note); verification scripts `verify/task3_check.js`, `task4_check.js`, `task5_check.js` (`NO_OLD` and `NEW` options).
- **Commands to verify**: API (from `api/`): `uv run pytest -q`; `uv run ruff check . && uv run ruff format --check .`; `curl -i http://localhost:8000/` (expects 307 to `/docs`). Web (from `web/`): `npm run build`; `npm run lint`; browser suites with `NO_OLD=1` (see the plan's Task 7 notes).
- **Test results**: API 111 passed, 0 failed, 2 deselected (e2e); ruff clean. Redirect and removed routes checked with curl. Browser, React app alone: sidebar 24 of 24, timeline 24 of 24, full input 13 of 13 on the dev server; timeline 24 of 24 and full input 13 of 13 on the production build. Web build and lint clean. SDK untouched.
- **Deviations from plan**: none new. The README gained a few more edits than listed (diagram, requirements, tests note), all to remove statements about the old arrangement.
- **Issues met along the way**: none in the app. After the run I found a `bob-chat-7` volume in the dev database; a read-only query showed it was created by the user's own live test (`openai-chat-example`, 4 calls), not by these checks.
- **Open issues / follow-ups**:
  - The user's API process on port 8000 runs the old code and returns 500 on `/` until restarted.
  - The web UI has no automated tests (deferred by decision), and the old-UI pixel comparison can no longer be re-run.
  - Only Chrome was used; no real OpenAI conversation was run through the React UI.

## Feature summary

All seven tasks are complete. The UI now lives in `web/` (React 19, TypeScript 6, Vite 8, React Router 8, about 20 source files, no runtime dependencies besides React and React Router). The API serves JSON and the OTLP receiver only.

- **API**: added `GET /api/conversations` and `trace_key` on `GET /api/calls/{id}`, CORS for the dev and preview origins, and `GET /` redirecting to `/docs`; removed the Jinja UI. Suite 143 to 111 tests (the 32 deleted cases were the old UI's own); no new tests by decision.
- **Parity**: 18 screens pixel-identical to the old UI on both the dev server and the production build, plus behaviour suites of 24, 24 and 13 checks; the intended differences are listed in Task 6 of the plan.
- **Verification record**: everything used in the browser checks is in `verify/` (scripts and logs), and the notes of each task say how to re-run it.
