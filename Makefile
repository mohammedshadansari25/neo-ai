.PHONY: up down logs migrate test-backend test-e2e openapi gen-types eval

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

migrate:
	docker compose exec backend alembic upgrade head

test-backend:
	docker compose exec backend pytest -v

openapi:
	docker compose exec backend python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > shared/openapi.json

gen-types:
	cd frontend && npx openapi-typescript ../shared/openapi.json -o src/api/schema.d.ts

eval:
	docker compose exec backend python -m evals.run_eval

test-e2e:
	cd frontend && npx playwright test
