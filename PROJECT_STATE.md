# PROJECT_STATE.md — Authoritative Build Baton

## Current Phase
DAY 3 IN PROGRESS (feat/day-3-hybrid-rag): Hybrid RAG implementation in progress.

## Completed Files
- **Day 0–1 (fully committed to main):** All Spikes A–G, DB Schema (Migration 0001), JWT Auth, LLM Gateway, React App Shell.
- **Day 2 (squash-merged into main):**
  - `backend/app/core/guards.py` (SHA-256 hashing, SSRF blocker, magic-byte validator)
  - `backend/app/schemas/capture.py` (request/response Pydantic v2 models + SSE event types)
  - `backend/app/api/routes/capture.py` (`/api/capture/text`, `/api/capture/url`, `/api/capture/file`)
  - `backend/app/worker/extraction.py` (Celery `extract_item_task`: text/url/pdf/image, Redis Stream SSE publish)
  - `backend/app/api/routes/events.py` (`/api/events/stream` JWT-scoped SSE with XREAD + heartbeat)
  - `backend/app/main.py` (registered capture + events routers)
  - `backend/tests/backend/test_capture.py` (SSRF unit tests, magic-byte tests, dedup + tenant-isolation integration tests)

## Active Endpoints & Migrations
- `/health/live`, `/health/ready`
- `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, `/api/me`
- `/api/capture/text`, `/api/capture/url`, `/api/capture/file`
- `/api/events/stream`
- `/api/memories` (create/list/get/delete)
- `/api/memories/search`
- Migration `0001_initial_schema` applied.

## Last Agent Completion Report
- Day 2 merged into main: migration 0001, capture routes, SSRF/magic-byte guards, Celery extraction, and SSE stream complete.
- Day 3 implementation is in progress on `feat/day-3-hybrid-rag`.
- Blocking Gate: run migration, Ruff, and the backend test suite before completion.

## Next Task
- Complete Day 3: embedding validation migration, Pydantic memory contracts, embedding service, hybrid RAG, memory routes, and focused tests.
