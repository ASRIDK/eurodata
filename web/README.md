# eurodata web platform

FastAPI backend + Next.js frontend over the `eurodata` Python API.

## Run (two terminals, from the repo root)

```bash
# backend — http://localhost:8000 (DB opened read-only)
source .venv/bin/activate
PYTHONPATH=src:. uvicorn web.backend.main:app --port 8000

# frontend — http://localhost:3000
cd web/frontend && npm run dev
```

## AI analyst

`/chat` talks to `POST /api/chat`, a Claude tool-use loop over read-only
`eurodata` tools. Configure in the backend environment (see `.env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5   # optional
```

Without a key the endpoint returns 503 and the chat page shows a clear
failure state; the rest of the site works regardless.

The assistant responds with typed blocks — `text`, `chart`, `table`,
`sources` (provenance chips, proxy-flagged), `warning`, `follow_ups` — which
the frontend renders directly; the model never draws its own tables.

## Layout

```
web/backend/    FastAPI: REST wrapper (main.py), chat loop (chat.py),
                whitelisted read-only tools (tools.py), shared handle (deps.py)
web/frontend/   Next.js App Router + Tailwind: / (home), /explore, /events,
                /chat; AIInput + hooks under src/components/
```

Frontend env: `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).
Tests: `python -m pytest -q tests/test_web_api.py tests/test_web_chat.py`.
