# Spike: does the sidebar list refresh only while Monitoring is open? (Task 2)

Risk from the plan: "Refresh only while open" relies on htmx trigger syntax that the in-process tests
(which cannot run JavaScript) cannot exercise.

## Method

1. Read the htmx 2.0.11 source (the version `base.html` loads) for how polling and conditions work.
2. Run the **exact HTML the template renders** (`partials/conversations.html`) in jsdom with the real
   `htmx.js`, with the poll interval shortened from 5s to 1s.
   - `spike/spike.js`: counts requests with the details closed, just opened, open, closed again, and with
     the list outside any `<details>`. Requests are counted and cancelled.
   - `spike/spike2.js`: a fake server answers every request with the fragment, so the list really
     replaces itself (`outerHTML`) many times; then checks nothing accumulates.

## Findings (htmx source)

- `every 5s [condition]` is supported. The condition runs with `this` = the element and a request is sent
  only when it returns exactly `true`. While it is `false` the timer keeps ticking but no request is sent.
- For a normal event the condition must come **directly after the event name**:
  `toggle[cond] from:closest details`. After `from:...` it is a syntax error.
- The condition used: `!this.closest('details:not([open])')`. It is `true` unless the list is inside a
  closed `<details>`, so it also polls when the list is not inside a `<details>` at all.

## Results (jsdom + htmx 2.0.11, all with 0 htmx errors)

| Situation | Requests | Expected |
|---|---|---|
| Details closed, 2.6s | 0 | 0 |
| Just opened (toggle event) | 1 | 1 |
| Open, 2.6s of polling (1s interval) | 3 | >= 2 |
| Closed again, 2.6s | 0 | 0 |
| List outside any details, 2.6s | 2 | >= 2 |
| Open, 6.5s, list replaced 7 times by the fake server | 7 | about 6, not growing |
| Re-opened after those 7 swaps | exactly 1 | 1 (more would mean ghost listeners) |

## Caveats

- jsdom is not a real browser. The manual browser checklist in Task 5 still applies.
- The harness needed three patches that are jsdom gaps, not problems in our markup:
  `XPathExpression.evaluate` default result type, a `CSS.escape` shim, and a fake `XMLHttpRequest`.
- A server-rendered `<details open>` cannot be relied on to fire `toggle` at page load (jsdom fired it
  once, but whether htmx has registered its listener by then is timing-dependent). The shell (Task 3)
  therefore needs its own guarded `load` trigger.

## Task 3: the real pages, then a real browser

### jsdom with the real pages (`spike/dump_pages.py`, `spike/spike3.js`)

The app renders `/`, `/volumes/alice-chat-42` and `/ui/conversations`; the page HTML runs in jsdom with
the real htmx (polling shortened to 1s) and a fake server that answers only `/ui/conversations`.

| Page | Result |
|---|---|
| `/volumes/alice-chat-42` (server-rendered `<details open>`) | shows "Loading…", then the 3 conversations with `alice-chat-42` marked `aria-current`; exactly one `#conversations`; polls while open; 0 requests while closed; exactly 1 on re-open; 0 htmx errors |
| `/` (`<details>` closed) | 0 requests in 2.6s and "Loading…" stays hidden; 1 request when the user opens it; list filled, nothing marked current |

- jsdom sent **2** initial requests on the open page (`load`, plus a `toggle` it fires for an initially-open
  `<details>`). Harmless: the GET is idempotent and the second response finds its target already replaced
  and is ignored. Real Chrome sent only 1 (below), so `hx-sync` was not added (it would also apply to the
  Load more button).
- Harness lesson: the first version of the fake server answered *every* path with the list, so the
  timeline's own 2s poller swapped the list into the timeline. That looked like a duplicate
  `#conversations` but was a harness bug, not an app bug.

### Real Chrome (`spike/browser.js`, puppeteer-core)

The app ran on port 8011 (read-only queries on the dev database) with the real 5s poll:

| Step | Sidebar requests | Expected |
|---|---|---|
| Home page, collapsed, at load and for 6.5s | 0 | 0 |
| Click Monitoring | 1 (3 conversations appear) | 1 |
| Open for 6s | 1 (the 5s refresh) | >= 1 |
| Collapse, wait 6.5s | 0 | 0 |
| Re-open | 1, still exactly one `#conversations` | 1 |
| Click `demo-conversation` | navigates to `/volumes/demo-conversation`, stays open, `demo-conversation` is current, 1 initial request | 1 or 2 |

Screenshots are in `spike/screenshots/` (light, dark, narrow 600px, home with Monitoring open in dark).
Dark mode only worked with puppeteer's `emulateMediaFeatures`; Chrome's `--blink-settings` flag left the
headless page light.

The only console error is `GET /favicon.ico` returning 404, which is unrelated: the app has no favicon.

## Task 5: the remaining browser checks, on throwaway data

Run in real Chrome against the real app on a **throwaway Postgres container** (port 5543, deleted
afterwards) and an in-memory trace store, so neither the dev database nor the dev MinIO bucket was touched.
40 conversations were seeded: 38 named `chat-NN`, one 77-character name, and `team/support`.
`spike/final_check.js` ran 23 checks; all passed:

| Area | What was checked |
|---|---|
| Landing | heading and hint; Monitoring collapsed; no sidebar request at load |
| Latest 30 | 30 of 40 shown, newest first (`team/support`, then the long name); subtitle `1 call · Oct 4, 09:39`; one `#conversations` |
| Long name | cut with an ellipsis, full name in the tooltip; no horizontal page scroll |
| Load more | button offered; after the click 40 shown, no duplicates, button gone, still one list |
| Slash name | link is `/volumes/team%2Fsupport`; its timeline opens with its message; Monitoring stays open and the entry is marked current |
| Live arrival | a genuine SDK-instrumented call for a new volume `bob-chat-7` was POSTed to the real `/v1/traces`; it appeared at the top of the open list by itself after 2.8s (the refresh is 5s), with no page reload; opening it shows its messages |
| Dark and narrow | dark theme renders; at 600px the sidebar stacks above the content with no horizontal scroll |
| Errors | no page or network errors (`/favicon.ico` excluded) |

Deviation from the plan's wording: the live-arrival check used the SDK's own instrumentation against a mocked
OpenAI response (`tests/spans.py`) instead of `examples/openai_chat.py`, because the latter needs a real
`OPENAI_API_KEY`. The SDK-to-API path with a real key is covered by the opt-in e2e tests, which were not run.

Screenshots: `spike/screenshots/final-*.png`.

## Re-running (needs Node and network once)

```bash
cd .claude/features/monitoring-sidebar/spike
npm i jsdom
curl -fsSLO https://cdn.jsdelivr.net/npm/htmx.org@2.0.11/dist/htmx.js
# render the fragment the way the app does:
(cd ../../../../api && uv run python -c "
from datetime import UTC, datetime
from app.repository import VolumeSummary
from app.ui import routes
now = datetime(2026, 10, 4, 10, 35, tzinfo=UTC)
print(routes.templates.get_template('partials/conversations.html').render(
    volumes=[VolumeSummary('alice-chat-42', 4, now, now)], has_more=True, can_load_more=True,
    limit=30, current='alice-chat-42', refresh_url='/ui/conversations?limit=30&current=alice-chat-42',
    more_url='/ui/conversations?limit=60&current=alice-chat-42', poll_seconds=5))
") > fragment.html
node spike.js && node spike2.js

# Task 3, real pages in jsdom (needs the dev database; renders the pages with the app):
(cd ../../../../api && PYTHONPATH=. uv run python ../.claude/features/monitoring-sidebar/spike/dump_pages.py ../.claude/features/monitoring-sidebar/spike)
node spike3.js

# Task 3, real Chrome: start the app (e.g. `cd api && uv run fastapi run app/main.py --port 8011`), then
npm i puppeteer-core && BASE=http://localhost:8011 node browser.js

# Task 5, throwaway database + in-memory store (the scripts hard-code port 5543 and 8011):
docker run -d --rm --name aicontrol-ui-check -e POSTGRES_USER=aicontrol -e POSTGRES_PASSWORD=aicontrol \
  -e POSTGRES_DB=aicontrol -p 127.0.0.1:5543:5432 postgres:16-alpine
cd ../../../../api
DATABASE_URL=postgresql+psycopg://aicontrol:aicontrol@localhost:5543/aicontrol uv run alembic upgrade head
S=../.claude/features/monitoring-sidebar/spike
PYTHONPATH=. uv run python $S/seed_ui_check.py
PYTHONPATH=. uv run python $S/launch_ui_check.py &        # serves http://127.0.0.1:8011
OUT=$S node $S/final_check.js                              # 23 checks (needs puppeteer-core)
# clean up: stop the app, then `docker stop aicontrol-ui-check`
```
