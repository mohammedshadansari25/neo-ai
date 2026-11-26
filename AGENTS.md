# AGENTS.md — Neo AI V1 Engineering Law

Read `AGENTS.md` and `PROJECT_STATE.md` completely before modifying any file.

## 1. Architecture Lock
- Modular monolith: `frontend/`, `backend/`, `postgres` (`pgvector/pgvector:pg17`), `redis` (`redis:7-alpine`).
- FORBIDDEN without an approved ADR: Neo4j, Qdrant, Pinecone, Milvus, MongoDB, S3, Kafka, Next.js, Zustand, Redux, WebSockets, or extra containers.
- Single sources of truth:
  - DB schema: `backend/app/db/models.py` + `backend/alembic/versions/`
  - API contract: FastAPI -> `shared/openapi.json` (`make openapi`)
  - Frontend types: `frontend/src/api/schema.d.ts` (`make gen-types`)

## 2. Hard Engineering Rules
1. Never invent database tables, columns, or API endpoints outside `DATA_MODEL.md` and `API_CONTRACTS.md`.
2. Never hardcode secrets or connection strings; load via `pydantic-settings` in `backend/app/config.py`.
3. Never bypass Pydantic v2 validation on API payloads, structured LLM extractions, or tool inputs.
4. Never trust LLM-supplied `user_id` values; inject `current_user.id` strictly from JWT auth and scope EVERY DB/vector/file query by `user_id`.
5. Never share async and sync SQLAlchemy engines: FastAPI uses `AsyncSessionLocal` (`asyncpg`); Celery uses `SyncSessionLocal` (`psycopg` + `NullPool`).
6. Never wrap LangGraph `interrupt()` or graph invocations in bare `except Exception:`.
7. Never execute mutating or external-write tools without a LangGraph `interrupt()` approval gate, deterministic `idempotency_key`, and postcondition DB verification.
8. Never add dependencies to `pyproject.toml` or `package.json` without logging justification in `PROJECT_STATE.md`.
9. Never modify files outside your assigned task's Allowed files list.
10. Never declare a task complete without executing and reporting required tests.

## 3. Public Repository Security Rules (Zero Tolerance)
- **Never** stage, commit, or push `.env`, API keys, JWT secrets, `backend/.venv/`, `frontend/node_modules/`, or `backend/data/uploads/`.
- Before every `git commit`, inspect `git diff --cached` and `git status` to verify only clean source, migration, test, and doc files are staged.
- Only `.env.example` (with placeholder values) may be committed.

## 4. Daily Issue -> Branch -> Atomic Commits -> PR Gate Loop
Never commit directly to `main`. For **Day X** of the 15-day plan:
1. **Start of Day (Issue & Branch):**
   - `git checkout main && git pull origin main`
   - `gh issue create --title "Day X: <Title>" --body "<Acceptance & deliverables>"`
   - `git checkout -b feat/day-X-<short-slug>`
2. **Implementation & Atomic Conventional Commits:**
   - Commit logical units (`feat(db): ...`, `feat(auth): ...`, `feat(rag): ...`, `feat(ui): ...`, `test(backend): ...`, `docs(state): ...`).
3. **Mandatory Local Verification Gate (Before Opening PR):**
   - `docker compose exec backend alembic upgrade head`
   - `docker compose exec backend ruff check app tests`
   - `docker compose exec backend pytest -v`
   - Contract sync whenever FastAPI routes/schemas change (`shared/openapi.json` -> `frontend/src/api/schema.d.ts`)
   - `cd frontend && npm run typecheck && npm run build`
   - Update `PROJECT_STATE.md` and commit it.
4. **Pull Request, CI Verification & Squash Merge:**
   - `git push -u origin feat/day-X-<short-slug>`
   - `gh pr create --title "feat(day-X): <Title>" --body "Closes #<ISSUE_NUMBER> ..."`
   - `gh pr checks --watch` (`backend-checks` and `frontend-checks`)
   - `gh pr merge --squash --delete-branch && git checkout main && git pull origin main`

## 5. Verification Commands
- Migrations: `docker compose exec backend alembic upgrade head`
- Backend tests: `docker compose exec backend pytest -v`
- Contract sync: `make openapi && make gen-types`
- Frontend check: `cd frontend && npm run typecheck && npm run build`
