> **Superseded (2026-10-04):** the server-rendered UI this plan built (`api/app/ui/`, Jinja + HTMX) was replaced by the React app in `web/` (see `.claude/features/react-web-ui/`). That code no longer exists; the scripts in `spike/` target it and are kept as history.

# Feature Plan: Monitoring Sidebar

## Overview

A left sidebar on every page of the web UI with a **Monitoring** button. Clicking it opens the saved
conversations (volumes); clicking one shows its timeline. The feature is almost entirely UI: the data
(name, call count, last activity) already exists in Postgres.

**Home page (`/`), Monitoring collapsed:**

```
 AIControl                  │
                            │  Monitoring
 ▸ Monitoring               │  Click Monitoring to browse your conversations.
                            │
                            │  Send calls from your code:
                            │    aicontrol.init(endpoint=…)
                            │    with aicontrol.volume("my-chat"): …
```

**A conversation page (`/volumes/alice-chat-42`), Monitoring open:**

```
 AIControl                  │ alice-chat-42                      4 calls
                            │
 ▾ Monitoring               │ 10:33  gpt-4o-mini   56 → 10 tok   ok
   ● alice-chat-42          │   system     You are a concise assistant.
     4 calls · Oct 4, 10:35 │   user       HELLO
   ○ demo-conversation      │   assistant  Hello! How can I assist you today?
     4 calls · Sep 24, 14:14│
   ○ smoke-test             │ 10:34  gpt-4o-mini   79 → 15 tok   ok
     2 calls · Sep 24, 14:03│   user       I AM FINE AND YOU
                            │   assistant  I'm doing well, thank you!
```

A **Load more** button appears under the list only when there are more than 30 conversations.

## Requirements Summary

| Question | Decision |
|---|---|
| Layout | **A**: Monitoring expands inside the sidebar (not a separate panel, not a separate page) |
| Entry label | Volume name, plus call count and date as a subtitle |
| Home page `/` | Landing page with a hint; the volumes table is removed |
| Freshness | List loads when Monitoring is opened, then refreshes about every 5s while open |
| Many conversations | Latest 30, plus a Load more button |
| Clicking a conversation | Normal link, full page load (existing URLs and bookmarks keep working) |

## Findings from exploration

- UI stack: Jinja2 templates + HTMX 2.0.11 (CDN), one plain CSS file with dark mode, no JS build step.
- Layout today: a top bar and one centered 960px column (`base.html`, `app.css`). No sidebar.
- Pages today: `/` (volumes table) and `/volumes/{name:path}` (live timeline polling every 2s).
- `repository.list_volumes` returns name, call count, created/last-activity for every volume, but counts
  every call in the database before sorting (fine for a home page, not for a sidebar polled every 5s).
- UI tests (`api/tests/integration/test_ui.py`) use an in-process client and assert on HTML text;
  one asserts that pages never read S3 (`NoReadStore`). The sidebar must stay index-only.
- `volume_name` URLs use the `urlpath` filter (`quote(s, safe="")`), so names containing `/` work.

## Architecture Decisions

1. **"Load more" raises a `limit` (30 → 60 → 90, capped at 500) and refetches the whole list**, instead
   of using keyset cursors like the timeline. Refresh and Load more then always render one consistent
   list. With cursors, a conversation that gets new activity jumps to the top and can appear twice or
   be skipped across pages.
2. **Counts are computed only for the visible conversations** (second query restricted to the page's
   volume ids, served by the `(volume_id, started_at, id)` index), instead of counting every call.
3. **Monitoring is a native `<details>` element**: no custom JavaScript, keyboard accessible, rendered
   `open` by the server on conversation pages.
4. **The top bar and breadcrumb are removed.** The brand moves into the sidebar; the highlighted entry
   replaces the breadcrumb.
5. **Dates are UTC** like the rest of the UI. Format "Oct 4, 10:35", full UTC time in a tooltip.
6. **Under 720px wide the sidebar stacks above the content.** No hamburger menu.
7. **The landing page keeps the SDK how-to snippet** from the old empty state.
8. **Sorted by most recent activity** (same order as `list_volumes`: `last_activity_at` descending, then name).

## Implementation Tasks

### Task 1: Repository query for the latest conversations

**Files to modify/create**:
- `api/app/repository.py` - add `VolumePage(items, has_more)` and `list_recent_volumes(session, limit)`
- `api/tests/integration/test_repository.py` - tests

**Implementation**:
1. Fetch `limit + 1` volumes in the existing order (`last_activity_at` descending nulls last, then name).
2. Run a second query counting calls only for those volume ids (`group by volume_id`).
3. Return `VolumePage(items=<first limit as VolumeSummary>, has_more=<got limit + 1>)`.

**Tests** (implement alongside):
- [x] Integration test: most recently active volume comes first (`test_list_recent_volumes_most_recent_first_with_counts`)
- [x] Integration test: `has_more` is false at exactly `limit` volumes and true at `limit + 1` (`test_list_recent_volumes_has_more_only_when_volumes_remain`)
- [x] Integration test: call counts are correct per volume (same test as the ordering one: new 1, mid 2, old 3)
- [x] Integration test: empty database returns an empty page (`test_list_recent_volumes_empty_database`)
- [x] Integration test: order and counts match the existing `list_volumes` for the same data (`test_list_recent_volumes_matches_list_volumes`)
- [x] Integration test (added): exactly two SQL statements run and the count statement is restricted with `volume_id IN (...)` (`test_list_recent_volumes_counts_only_the_returned_volumes`)

**Acceptance criteria**:
- [x] Tests pass
- [x] The count query is restricted to the page's volumes

**Status**: Completed

**Completion Notes**:
- **Files modified**: `api/app/repository.py` (new `VolumePage` dataclass and `list_recent_volumes`), `api/tests/integration/test_repository.py` (5 tests, `seed_volumes` helper, `sqlalchemy.event` import).
- **Key decisions**: two queries (volumes with `limit + 1`, then counts for just those ids). Same ordering as `list_volumes` (`last_activity_at` descending nulls last, then name). A volume with no stored calls gets `call_count = 0`.
- **Not validated here**: `limit` goes straight into SQL (`limit + 1`). The route in Task 2 must enforce `ge=1, le=500`.
- **Patterns established**: a performance guard test that records SQL through `event.listen(session.bind.sync_engine, "before_cursor_execute", ...)`.
- **Test utilities added**: `seed_volumes(session)` in `test_repository.py` (old = 3 calls, mid = 2 calls, new = 1 call, newest last). Gotcha: `(trace_id, span_id)` is unique across ALL volumes and `spans()` reuses the same ids, so a second volume built with `spans()` is silently dropped as duplicates. Give each volume its own span ids.
- **Integration points**: Task 2 calls `repo.list_recent_volumes(session, limit)` and reads `page.items` (`VolumeSummary`: `name`, `call_count`, `created_at`, `last_activity_at`) and `page.has_more`.
- **Notes for next task**: `last_activity_at` is nullable in the model (never null in practice, since `upsert_volume` always sets it), so the `short_utc` filter must accept `None`.

### Task 2: Conversations fragment `GET /ui/conversations`

**Files to modify/create**:
- `api/app/ui/routes.py` - route, constants (`SIDEBAR_PAGE_SIZE = 30`, `SIDEBAR_MAX = 500`, `SIDEBAR_POLL_SECONDS = 5`), `short_utc` filter
- `api/app/ui/templates/partials/conversations.html` - new fragment
- `api/tests/integration/test_ui.py` - tests

**Implementation**:
1. Query params: `limit` (default 30, `ge=1`, `le=500`) and `current` (name of the open conversation).
2. Return the whole list element, containing for each conversation: a link to `/volumes/<urlpath name>`
   (name truncated by CSS, full name in `title`), a subtitle "N calls · date" ("1 call" in the singular,
   UTC, full time in a tooltip), and `aria-current="page"` on the current entry.
3. When `has_more`, add a **Load more** button that replaces the whole list with `limit + 30`.
4. The list element carries its own refresh attributes (same `limit`), so a Load more response also
   updates what the refresh requests.
5. Empty state text when there are no conversations.

**Tests** (implement alongside):
- [x] Integration test: most-recent first (`test_conversations_most_recent_first_with_counts_and_dates`) and encoded links, `team/support` → `team%2Fsupport` (`test_conversation_links_are_encoded`)
- [x] Integration test: counts, singular/plural and UTC dates with tooltip (same test as the ordering one)
- [x] Integration test: current conversation carries `aria-current="page"` (`test_current_conversation_is_marked`)
- [x] Integration test: Load more present with `limit=60` when there are more than 30; absent otherwise (`test_load_more_grows_the_list_and_keeps_current`)
- [x] Integration test: `limit=501` and `limit=0` are rejected, plus `limit=-1` (`test_conversations_limit_is_validated`)
- [x] Integration test: conversation names are HTML-escaped (`test_conversation_names_are_escaped`)
- [x] Integration test: no reads from S3 (`NoReadStore.reads == 0`, asserted in the ordering test)
- [x] Integration test: empty state text (`test_conversations_empty_state`)
- [x] Take over the checks of `test_volumes_page_lists_volumes_with_links` (links, in `test_conversation_links_are_encoded`) and of the first assertion of `test_empty_states` (`test_conversations_empty_state`). The two old tests still pass because `/` still shows the table; Task 4 replaces them.
- [x] Added: the list refreshes itself only while open (`test_conversations_list_refreshes_itself_only_while_open`)
- [x] Added: Load more stops at the maximum with a note (`test_load_more_stops_at_the_maximum`)
- [x] Added (spike, not a pytest test): the trigger behaves correctly with real htmx in jsdom, see `monitoring-sidebar-htmx-spike.md`

**Acceptance criteria**:
- [x] The fragment alone renders a complete, correct list
- [x] Tests pass

**Status**: Completed

**Completion Notes**:
- **Files created/modified**: `api/app/ui/routes.py` (constants `SIDEBAR_PAGE_SIZE = 30`, `SIDEBAR_MAX = 500`, `SIDEBAR_POLL_SECONDS = 5`; route `conversations_fragment`; helper `_conversations_url`; `_short_utc` registered as the `short_utc` filter), `api/app/ui/templates/partials/conversations.html` (new), `api/tests/integration/test_ui.py` (9 new test functions = 11 cases, helpers `conversation_names`, `attr_url`, `store_volumes`), spike scripts in `.claude/features/monitoring-sidebar/spike/`.
- **Key decisions**: the fragment IS the whole `<ul id="conversations">` and replaces itself (`hx-swap="outerHTML"`), so refresh and Load more always carry a consistent `limit`. Load more is a button inside the list requesting `limit + 30`, capped at `SIDEBAR_MAX`; at the cap a note "Showing the latest N conversations." replaces the button. `current` is kept in both URLs.
- **Patterns established**: the guard `[!this.closest('details:not([open])')]` on both triggers means nothing is requested while the enclosing `<details>` is closed (and it still polls when the list is not inside a `<details>`). htmx syntax: the condition directly after the event name, `toggle[cond] from:closest details`; for polling it follows the interval, `every 5s [cond]`.
- **Test utilities added**: `store_volumes(session_factory, store, names)` (one call per volume, volume i active at T0 + i minutes, so the last name is newest), `conversation_names(html)`, `attr_url(html, pattern)`.
- **CSS hooks the fragment emits (for Task 3)**: `.conversations` (the `ul`), `.conversation` and `.conversation.current` (the link), `.conv-name`, `.conv-meta`, `li.empty`, `li.more button.link`, `li.note`.
- **Notes for next task (Task 3)**:
  1. The shell's placeholder `<ul id="conversations">` must carry `hx-get="/ui/conversations?limit=30&current=<encoded name>"` and the same two triggers **plus a guarded `load` trigger** (`load[!this.closest('details:not([open])')]`). Do not rely on the browser firing `toggle` for a server-rendered `<details open>`.
  2. Build that URL with the same `urlencode` logic (`_conversations_url`) and pass it to `base.html`, so `current` is encoded the same way.
  3. The global `.empty` CSS rule (`color: var(--muted)`) also applies to the sidebar's empty `li`.
  4. The old tests `test_volumes_page_lists_volumes_with_links` and `test_empty_states` still describe the old `/` table. Task 4 replaces them; move their htmx script and `integrity` assertion to the Task 3 or Task 4 tests.
  5. Re-run the jsdom spike against the new shell (see the spike document).

### Task 3: Page shell and styles

**Files to modify/create**:
- `api/app/ui/templates/base.html` - two-column shell with the sidebar
- `api/app/ui/templates/volume_timeline.html` - drop the breadcrumb block
- `api/app/ui/static/app.css` - layout, sidebar, dark mode, responsive
- `api/app/ui/routes.py` - `volume_page` passes `current_volume`
- `api/tests/integration/test_ui.py` - tests

**Implementation**:
1. Two-column grid: sticky full-height scrollable sidebar + content (`main`, max-width kept).
2. Sidebar: brand link, then `<details id="monitoring">` with a `<summary>` "Monitoring" and an empty
   list that requests `/ui/conversations` when opened and every 5s only while open.
3. `volume_page` passes `current_volume`; the template renders `<details open>` and sends
   `current=<name>` (URL-encoded).
4. CSS reuses the existing colour variables (dark mode for free); under 720px the sidebar stacks above.
5. Remove the top bar and the `breadcrumb` block.

**Tests** (implement alongside):
- [x] Integration test: every page contains the sidebar and the Monitoring summary, the brand, no top bar (`test_every_page_has_the_sidebar_and_no_top_bar`, for `/` and `/volumes/alice-chat-42`)
- [x] Integration test: `/volumes/alice-chat-42` is rendered open and requests `current=alice-chat-42`, with the guarded `load`, `toggle` and 5s triggers and a "Loading…" placeholder (`test_conversation_page_opens_monitoring_and_loads_the_list_at_once`)
- [x] Integration test: a slash name stays URL-encoded (`test_sidebar_url_keeps_slash_names_encoded`)
- [x] Integration test: `/` is rendered closed and fetches nothing yet (`test_home_page_keeps_monitoring_closed_and_fetches_nothing_yet`)
- [x] Integration test: htmx script tag with its `integrity` attribute is still present (inside `test_every_page_has_the_sidebar_and_no_top_bar`)
- [x] Integration test: `/static/app.css` contains the sidebar rules (`test_static_css_has_the_sidebar_layout`; the existing dark-mode check is kept)
- [x] Added: a hostile volume name cannot break out of the sidebar URL (`test_hostile_volume_name_cannot_break_out_of_the_sidebar`)
- [x] Added (not pytest): real pages in jsdom and a real-Chrome click-through, see `monitoring-sidebar-htmx-spike.md`

**Acceptance criteria**:
- [x] Tests pass
- [x] Existing timeline tests still pass unchanged (no existing test was edited)

**Status**: Completed

**Completion Notes**:
- **Files created/modified**: `api/app/ui/templates/base.html` (rewritten: two-column shell, no top bar), `api/app/ui/templates/partials/conversation_list.html` (new macro), `api/app/ui/templates/partials/conversations.html` (now uses the macro), `api/app/ui/templates/volume_timeline.html` (breadcrumb block removed), `api/app/ui/static/app.css` (layout, sidebar, responsive; `.topbar` removed), `api/app/ui/routes.py` (`current_volume` in `volume_page`, template globals `sidebar_url` and `sidebar_poll_seconds`), `api/tests/integration/test_ui.py` (7 new cases).
- **Key decisions**: the list element is one macro, `conversation_list(refresh_url, poll_seconds, load=False)`, used with `{% call %}` by both the shell (empty, `load=True`) and the fragment, so the triggers are defined once. The shell shows "Loading…" until the first response. `<details>` is open exactly when the route passes `current_volume`. The brand lives in the sidebar; the top bar and breadcrumb are gone.
- **Change to Task 2 code**: the fragment no longer gets `poll_seconds` from its route; it uses the `sidebar_poll_seconds` global like the shell.
- **Patterns established**: any page extending `base.html` only needs to pass `current_volume` (omit it for no current conversation); the sidebar URL comes from the `sidebar_url(current_volume)` global.
- **Known behavior**: in jsdom an open page requests the list twice (`load` plus an initial `toggle`); in real Chrome it is once. Harmless either way (idempotent GET, the second response is ignored), so no `hx-sync`.
- **Verified beyond the tests**: real Chrome click-through (collapsed = 0 requests over 6.5s, click = 1, refresh while open, collapse = 0, re-open = 1, navigation keeps it open and highlights the current one), plus light, dark and 600px screenshots in `spike/screenshots/`. This covers manual checklist items 2, 3, 5, 7 and 8 of Task 5 for the 3-conversation data set.
- **Notes for next task (Task 4)**: `volumes_page` still renders `volumes.html` (the table, now inside the shell) with a DB session. Replace it with `landing.html`, drop the session dependency, and delete `volumes.html`. The landing must not set `current_volume`. The old tests `test_volumes_page_lists_volumes_with_links` and the first assertion of `test_empty_states` still pass against the table and must be rewritten there; their htmx assertion is already covered by `test_every_page_has_the_sidebar_and_no_top_bar`.
- **Still open for Task 5**: the "Load more" flow (needs 31+ conversations), the live arrival of a new conversation (`bob-chat-7`) and a slash name such as `team/support` (the dev database has none) have not been seen in a browser; `/favicon.ico` returns 404 (pre-existing, unrelated).

### Task 4: Landing page at `/`

**Files to modify/create**:
- `api/app/ui/routes.py` - `volumes_page` becomes the landing route and no longer needs a database session
- `api/app/ui/templates/landing.html` - new; hint + SDK how-to snippet
- `api/app/ui/templates/volumes.html` - delete
- `api/tests/integration/test_ui.py` - tests

**Implementation**:
1. Landing shows "Click Monitoring to browse your conversations" and the SDK snippet.
2. The route does not query the database.

**Tests** (implement alongside):
- [x] Integration test: `/` returns 200 with the hint and the snippet (`test_home_page_is_a_landing_page_without_the_conversation_list`)
- [x] Integration test: no conversation names appear on `/` even when conversations exist (same test, with the 3 seeded conversations)
- [x] Integration test: no reads from S3 (same test, `NoReadStore.reads == 0`)
- [x] Integration test: the old table-specific tests are rewritten, none deleted without replacement (see the completion notes)
- [x] Added: `/` never opens a database session (`test_home_page_does_not_touch_the_database`, using a session factory that raises)

**Acceptance criteria**:
- [x] Tests pass

**Status**: Completed

**Completion Notes**:
- **Files created/modified**: `api/app/ui/routes.py` (`volumes_page(request, session)` became `landing_page(request)` with no session dependency; module docstring updated), `api/app/ui/templates/landing.html` (new), `api/app/ui/templates/volumes.html` (deleted), `api/app/ui/static/app.css` (removed `table.volumes`, `.volumes th/td` and `.num`, which only the table used), `api/tests/integration/test_ui.py`.
- **How the two old tests were replaced**:
  - `test_volumes_page_lists_volumes_with_links` became `test_home_page_is_a_landing_page_without_the_conversation_list`. Its link assertions now live in `test_conversation_links_are_encoded` (Task 2) and its htmx script and `integrity` assertion in `test_every_page_has_the_sidebar_and_no_top_bar` (Task 3).
  - The first assertion of `test_empty_states` ("No volumes yet") now checks that the landing renders with no data. The list's own empty state is `test_conversations_empty_state` (Task 2).
- **Key decisions**: landing = `<h1>Monitoring</h1>`, "Click Monitoring to browse your conversations.", and the SDK how-to snippet kept from the old empty state under "Send calls from your code". Page title "AIControl". The landing sets no `current_volume`. `repo.list_volumes` is untouched because the REST `/api/volumes` still uses it.
- **Verified beyond the tests**: real Chrome shows the landing as in the plan's mockup, with 0 sidebar requests at load; clicking Monitoring lists the 3 conversations; no page errors apart from the unrelated `/favicon.ico` 404. Screenshots: `spike/screenshots/landing-closed.png` and `landing-open.png`.
- **Notes for next task (Task 5)**:
  1. `README.md` line 33 still says `# UI: volumes → live timeline → "Show full input"`; update it and any other UI wording.
  2. Still not seen in a browser: Load more with 31+ conversations, a new conversation appearing live, and a slash name such as `team/support`. Do these against a throwaway Postgres container (migrations applied, data seeded with `repo.insert_calls`), not the dev database, so nothing is written to it.
  3. The real-Chrome scripts in `spike/` (`browser.js`) can be pointed at that throwaway app with `BASE=...`.

### Task 5: Verification and docs

**Files to modify/create**:
- `README.md` - describe the sidebar in the UI parts ("UI: volumes → live timeline" and similar)

**Implementation**:
1. Update the README wording.
2. Run `uv run pytest` and `uv run ruff check . && uv run ruff format --check .` in `api/`.
3. Manual browser checklist (the in-process tests cannot run JavaScript):
   1. `/` shows the landing page.
   2. Clicking Monitoring shows the list.
   3. Clicking a conversation opens it with Monitoring open and the entry highlighted.
   4. Running `examples/openai_chat.py --volume bob-chat-7` makes `bob-chat-7` appear within about 5s.
   5. Collapsing Monitoring stops the refresh requests (browser network tab).
   6. With 40 seeded volumes, Load more goes from 30 to 40.
   7. Dark mode.
   8. A window narrower than 720px.
   9. A slash name such as `team/support`.

**Acceptance criteria**:
- [x] Full test suite and lint pass
- [x] Every item of the manual checklist is confirmed (in Chrome; see the table below)

**Status**: Completed

**Completion Notes**:
- **Files modified**: `README.md` (the UI line in the quickstart now reads "Monitoring sidebar → conversation → live timeline → Show full input", plus a new "Web UI" section). Spike scripts, notes and screenshots in `.claude/features/monitoring-sidebar/spike/` and `monitoring-sidebar-htmx-spike.md`.
- **Results**: API suite 143 passed (2 e2e deselected), ruff check and format clean. The untouched SDK suite 34 passed. Browser checks 23 of 23 passed.
- **Where each manual checklist item was verified (real Chrome)**:
  1. Landing page: Task 4 and Task 5 run.
  2. Clicking Monitoring shows the list: Task 3 and Task 5 run.
  3. Clicking a conversation keeps Monitoring open and highlights it: Task 3 and Task 5 run.
  4. A new conversation appears by itself: Task 5 run, `bob-chat-7` appeared after 2.8s at the top, no page reload.
  5. Collapsing stops the refresh: Task 3 run, 0 requests over 6.5s with a real 5s poll.
  6. Load more: Task 5 run, 40 seeded conversations, 30 shown then 40, no duplicates, button gone.
  7. Dark mode: Task 3 and Task 5 runs.
  8. Narrow window: Task 3 and Task 5 runs, stacked, no horizontal scroll.
  9. Slash name `team/support`: Task 5 run, encoded link, timeline opens, entry marked current.
- **Deviations**: item 4 sent a genuine SDK-instrumented call (mocked OpenAI response) to the real `/v1/traces` instead of running `examples/openai_chat.py`, which needs a real `OPENAI_API_KEY`. The checks ran against a throwaway Postgres and an in-memory trace store, so the dev database and MinIO were never touched.
- **Not done**: the opt-in e2e tests (need `OPENAI_API_KEY`; no SDK or ingest code changed). Firefox and Safari were not tested, only Chrome.
- **Risks from the plan**: the "refresh only while open" risk is retired (it behaved correctly in Chrome and no fallback was needed); the "removing the top bar changes every page" risk was covered by the browser runs.
- **Known leftovers**: `/favicon.ico` returns 404 (pre-existing, unrelated).

## Risks and Mitigations

- **"Refresh only while open" relies on htmx trigger syntax the in-process tests cannot exercise.**
  Covered by manual checklist item 5. Fallback: refresh always (one small query every 5s per open tab),
  acceptable for a local monitoring tool.
- **Sorting by `last_activity_at` has no index.** Fine until there are very many conversations; add an
  index then.
- **Removing the top bar changes every page.** Existing tests check content, not layout, so the manual
  check matters.
- **Date format omits the year.** The tooltip carries the full date.
- **Load more refetches the whole list each time** (at most 500 small rows). Accepted in exchange for a
  consistent list while it refreshes.

## Out of Scope

- Search or filtering conversations
- First-message titles
- Smooth page swaps without reload
- Renaming or deleting conversations
- Other sidebar buttons (for example Evaluation)
- Remembering the open/closed state across visits
- Authentication or per-user filtering
- A hamburger menu on mobile
- An index on `last_activity_at`
