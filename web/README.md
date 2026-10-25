# AIControl web UI

React + TypeScript (Vite) front end for the AIControl API, built with the
[Carbon Design System](https://carbondesignsystem.com) (`@carbon/react`). It only reads: the API
receives the calls from the SDK, this app lets you browse them.

## Run it

```bash
# terminal 1: the API (from the repository root)
cd api && uv run fastapi run app/main.py --port 8000

# terminal 2: this app
cd web
npm install
npm run dev          # http://localhost:5173
```

Needs Node >= 22.22 (React Router 8).

## Configuration

| Where | Setting | Default |
|---|---|---|
| web (`.env.local`, see `.env.example`) | `VITE_API_URL`: where the API is | `http://localhost:8000` |
| API (environment or root `.env`) | `CORS_ORIGINS`: origins allowed to call the API, a JSON list | the dev server (`localhost` and `127.0.0.1` on 5173) and `npm run preview` (same hosts on 4173) |

If the UI runs on another address, add it to `CORS_ORIGINS`; the browser blocks calls otherwise (the
UI then shows "Cannot reach the API"). `VITE_API_URL` is read when the app is built, so set it before
`npm run build`.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload (port 5173) |
| `npm run build` | Type-check, then build to `dist/` |
| `npm run preview` | Serve the build (port 4173) |
| `npm run lint` | oxlint |

## Layout

```
src/
├── main.tsx, App.tsx     router and routes
├── api/                  types.ts (API shapes) and client.ts (typed fetch)
├── components/           Layout (Carbon UI shell), Sidebar (the Observe link), ConversationColumn, ProjectsProvider/ProjectSwitcher (header)/NewProjectModal, CallCard, TraceTree (tree + detail pane), ...
├── pages/                Landing, ObservePage (conversations column + page), ProjectPage, VolumePage, NotFound
├── hooks/                small hooks (title, current project and conversation, projects, polling)
├── lib/                  format.ts (UTC dates, JSON, durations), traces.ts (calls grouped into traces)
└── styles/app.scss       Carbon styles, dark theme and the app's own rules
```

## Styling

The UI uses Carbon components and tokens. It follows the operating system's light or dark setting
(Carbon's White and Gray 100 themes). `app.scss` imports only the Carbon styles of the components
in use, which keeps the CSS at about a third of the full library; **when you use a Carbon component
that is not styled yet, add its `@use '@carbon/react/scss/components/<name>'` line there.** The IBM
Plex fonts are self-hosted through `@fontsource`.

Addresses: `/` (back to the last project, or the project list), `/projects/<project>` (the project's home) and `/projects/<project>/volumes/<name>` (a conversation). A project is addressed by its **slug** (`/projects/my-project`), the name is only a label shown in the UI; conversation names are percent-encoded (`team%2Fsupport`). The last project opened is remembered in the browser's `localStorage` (guarded: the app works without it).
