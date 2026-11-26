# PROJECT_STATE.md — Authoritative Build Baton

## Current Phase
DAY 1 COMPLETE (pending frontend build check): Core DB (Migration 0001), JWT/Refresh Auth, LLM Gateway, and React Dark-Mode App Shell + LoginPage.

## Completed Files
- **Day 0 (ALL 7 SPIKES PASSED):** `spike_{a,b,c,d,e,g}_*.py` (6/6 passed), `shared/openapi.json` + `frontend/src/api/schema.d.ts` (`tsc --noEmit` 0 errors).
- **Day 1 Step 1 (VERIFIED):** `models.py`, `session.py`, `0001_initial_schema.py` (`alembic upgrade head` passed), `security.py`, `auth.py`, `test_migrations.py` + `test_auth.py` (`2 passed in 1.16s`).
- **Day 1 Step 2:** `frontend/index.html`, `frontend/src/index.css`, `frontend/src/api/client.ts`, `frontend/src/context/AuthContext.tsx`, `frontend/src/components/ErrorBoundary.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/App.tsx`, `frontend/src/main.tsx`.

## Active Endpoints & Migrations
- `/health/live`, `/health/ready`
- `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, `/api/me`
- Migration `0001_initial_schema` applied (`head`).

## Last Agent Completion Report
- Agent: Neo AI V1 Build Lead
- Tests Executed: `pytest -v tests/backend` (`2 passed`), `openapi-typescript`, `tsc --noEmit` (0 errors).
- Blocking Gate: Run `npm run typecheck && npm run build` in `frontend/`.

## Next Task
- Verify frontend build, then begin **Day 2 (Universal Capture `/api/capture/{text,url,file}`, Magic-byte/SSRF guards, `content_hash` dedup, Celery task, and SSE `/api/events/stream`)**.
