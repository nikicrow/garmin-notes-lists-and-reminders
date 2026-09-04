# Tuck Development Guide

## Project overview

Tuck is a private notes, lists, and reminders application. The repository currently contains:

- `backend/`: Python 3.11 FastAPI service managed with `uv`.
- `frontend/`: React 19, TypeScript, and Vite client managed with `pnpm`.

Keep product and architecture documentation focused on current behavior. Git history is the record of superseded designs.

## Setup

Install dependencies from the committed lockfiles:

```bash
make install
```

This runs `uv sync --frozen` in `backend/` and `pnpm install --frozen-lockfile` in `frontend/`.

## Development commands

Run from the repository root:

```bash
make dev-api       # FastAPI development server
make dev-web       # Vite development server
make format        # Apply Ruff and Prettier formatting
make format-check  # Check formatting without modifying files
make lint          # Ruff and ESLint
make typecheck     # strict mypy and TypeScript checks
make test          # Pytest and Vitest
make build         # TypeScript and Vite production build
make check         # all formatting, lint, type, test, and build checks
```

## Conventions

- Use test-driven development for behavior changes: verify a focused test fails, implement the minimum change, then run the full relevant checks.
- Keep the backend under `backend/src/tuck_api/`; place backend tests in `backend/tests/`.
- Keep frontend application code and colocated component tests under `frontend/src/`.
- Add API routes under `/api/v1/`; `/api/v1/health` is the service liveness endpoint.
- Preserve strict typing. Avoid weakening mypy, TypeScript, Ruff, or ESLint rules to make checks pass.
- Update `uv.lock` or `pnpm-lock.yaml` whenever dependencies change, and verify frozen installs.
- Do not commit generated or local state such as `.venv/`, `node_modules/`, `dist/`, caches, editor settings, or `.env*` secrets.
- Prefer small, focused conventional commits.

## Before committing

Run:

```bash
make check
git diff --check
```
