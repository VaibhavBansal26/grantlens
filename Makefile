.PHONY: up down test lint eval
up: ; docker compose up --build
down: ; docker compose down
test: ; cd apps/api && uv run pytest
lint: ; cd apps/api && uv run ruff check .
eval: ; @echo "Phase 2: evaluation harness not built yet"
