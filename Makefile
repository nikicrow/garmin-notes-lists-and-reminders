.PHONY: install format format-check lint typecheck test build check dev-api dev-web

install:
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile

format:
	cd backend && uv run ruff format .
	cd frontend && pnpm format

format-check:
	cd backend && uv run ruff format --check .
	cd frontend && pnpm format:check

lint:
	cd backend && uv run ruff check .
	cd frontend && pnpm lint

typecheck:
	cd backend && uv run mypy
	cd frontend && pnpm typecheck

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

build:
	cd frontend && pnpm build

check: format-check lint typecheck test build

dev-api:
	cd backend && uv run uvicorn tuck_api.main:app --reload

dev-web:
	cd frontend && pnpm dev
