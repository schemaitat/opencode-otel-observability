# Trace Explorer — Frontend

React + TypeScript + Vite SPA for the [Trace Explorer](../../README.md#trace-explorer), part of the
OpenCode Observability Stack. It talks to the FastAPI backend in [`../backend`](../backend) (which
in turn queries Tempo) and renders:

- A **Sessions** view with a session list, nested span waterfall, and per-span detail panel
- An **Overview** dashboard with cost/token/tool-usage charts and tables across all sessions

## Development

Run the full stack first (`just up` from the repo root), then start the backend and frontend
locally with hot reload:

```bash
just dev-trace-explorer
```

Or run the frontend alone (requires the backend to be running, e.g. via `docker compose up -d`):

```bash
npm install
npm run dev
```

By default the frontend talks to the backend at the same origin. To point it at a different
backend, set `VITE_API_URL`:

```bash
VITE_API_URL=http://localhost:8060 npm run dev
```

## Scripts

- `npm run dev` — start the Vite dev server
- `npm run build` — type-check and build for production (output in `dist/`)
- `npm run lint` — run ESLint
- `npm run preview` — preview the production build locally

## Stack

- [React 19](https://react.dev) + [TypeScript](https://www.typescriptlang.org)
- [Vite](https://vite.dev) for dev server and bundling
- [Tailwind CSS](https://tailwindcss.com) for styling
- [Recharts](https://recharts.org) for the Overview charts
- [lucide-react](https://lucide.dev) for icons
