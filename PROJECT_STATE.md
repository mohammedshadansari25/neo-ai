# PROJECT_STATE.md — Authoritative Build Baton

## Current Phase
DAY 2 IN PROGRESS (feat/day-2-capture-and-sse): Universal Capture, SSRF Guards & SSE Bus built. Pending verification.

## Completed Files
- **Day 0–1 (fully committed to main):** All Spikes A–G, DB Schema (Migration 0001), JWT Auth, LLM Gateway, React App Shell.
- **Day 2 (on feat/day-2-capture-and-sse):**
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
- Migration `0001_initial_schema` applied.

## Last Agent Completion Report
- Tests Executed: Day 0 (6 spikes), Day 1 (2 backend tests). Day 2 tests pending Docker run.
- Blocking Gate: `docker compose exec backend pytest -v tests/backend` must show all tests passing.

## Next Task
- Verify Day 2 tests -> commit -> `git push` -> `gh pr create` -> CI pass -> squash merge.
- Then begin **Day 3: Hybrid RAG (BM25/FTS + HNSW iterative scan + RRF + dedup + conflict detection)**.
