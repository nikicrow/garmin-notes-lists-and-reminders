# Tuck Deployment

## Overview

Tuck runs as three containerized services on a single host inside the home tailnet:

- **PostgreSQL 17** — application database
- **FastAPI** — REST API and business logic
- **nginx** — static PWA assets plus API proxy

The compose file at the repository root defines all three services and is the single source of truth for the container layout. Read that file first when changing the deployment.

## Prerequisites

- Docker (or Podman + podman-compose) on the host
- Tailscale client authenticated and present on the host
- Tailscale Serve enabled for the HTTP port you want to expose
- A Tailnet machine (e.g. `fedora-1`) that is always on and reachable from the tailnet

## Quick start (local development)

```bash
cd /path/to/tuck/repo
cp .env.example .env
docker compose up -d postgres
docker compose ps
```

The database port binds only to localhost. Compose reports the service healthy only after `pg_isready` accepts connections. `GET /api/v1/health` is a liveness check that does not depend on configuration or PostgreSQL. `GET /api/v1/ready` validates application settings and reports ready; it returns `503 Service Unavailable` when configuration is missing or invalid.

Stop the service with `docker compose down`. Add `--volumes` only when the local development data should be deleted.

## Service contents

### PostgreSQL

Image `postgres:17-alpine`. Stores all application data in a named volume `tuck-postgres-data`.

Environment variables:
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `POSTGRES_PORT` (for host-side port mapping)

Healthcheck runs `pg_isready` against the configured user and database.

### API (FastAPI)

Built from `backend/Dockerfile`. Connects to PostgreSQL using the `DATABASE_URL` environment variable.

On startup the container:
1. Runs `alembic upgrade head` to apply any pending migrations.
2. Starts `uvicorn tuck_api.main:app` on port 8000.

Health endpoints:
- `GET /api/v1/health` — liveness, no dependency on database
- `GET /api/v1/ready` — readiness, validates configuration; returns 503 if invalid

Liveness and readiness should be monitored by the host orchestrator. The compose healthcheck queries `/api/v1/health`.

### Web (nginx)

Image `nginx:alpine`. Serves the built PWA from `frontend/dist` and proxies `/api/` requests to the FastAPI service.

The nginx configuration lives at `docker/web/nginx.conf`. It is mounted read-only into the container.

## Secrets and configuration

All configuration is supplied through environment variables. The repository ships a `.env.example` with safe non-production defaults. Copy it to `.env` and adjust for your environment.

**Production secrets that MUST NOT be committed:**
- `POSTGRES_PASSWORD`
- `TUCK_SECRET_KEY`
- Any real hostnames, tailnet identifiers, or credentials

The compose file reads these from the host environment or `.env` file. For production deployments, consider one of:
- A host-level `.env` file with restricted permissions (`chmod 600 .env`)
- Docker secrets if running in swarm mode
- An external secret manager integrated through the environment

The `.env.example` file is the template. The `.env` file is `.gitignore`d and must never be committed.

## Startup sequence and migrations

The API service depends on PostgreSQL and waits for the `service_healthy` condition before starting. During startup the API container runs Alembic migrations before the application server starts.

This means:
- First startup creates the schema automatically.
- Subsequent startups apply any new migrations from the `backend/migrations` directory.
- Migrations run as part of the container entrypoint; they are not separate manual steps.

If a migration fails, the API container exits. Check logs with `docker compose logs api`.

## Health checks

| Service | Healthcheck | Endpoint/command |
|---------|-------------|------------------|
| postgres | `pg_isready` | Direct PostgreSQL check |
| api | HTTP GET | `/api/v1/health` |
| web | HTTP GET | `/` (nginx returns 200) |

The API also exposes `/api/v1/ready` for deeper readiness probing. A full operational probe should check both:
1. `GET /api/v1/health` → 200
2. `GET /api/v1/ready` → 200

## Logs

All services log to stdout/stderr, captured by the container runtime. Use:

```bash
docker compose logs -f          # all services
docker compose logs -f api      # API only
docker compose logs -f postgres # PostgreSQL only
```

Compose is configured with rotated json-file logging (10 MB max, 3 files) to avoid unbounded disk growth.

## Update sequence

To update Tuck to a new version:

```bash
# 1. Pull or check out the desired code
git pull   # or checkout a tagged release

# 2. Rebuild the API image (if the backend changed)
docker compose build api

# 3. Recreate the services
docker compose up -d

# 4. Watch the startup logs for migration status
docker compose logs -f api
```

The API container always runs migrations on startup, so schema changes are applied automatically when the new image starts.

## Backup and restore

See `scripts/postgres-backup.sh` and `scripts/postgres-restore.sh` for the backup/restore tooling. Those scripts are documented in the Operator Runbook.

## Testing the deployment

The repository has tests that validate the deployment configuration:

```bash
cd backend
uv run pytest tests/test_deployment.py tests/test_backup_restore.py -v
```

These tests check:
- compose.yaml parses without errors
- All required services are defined (postgres, api, web)
- PostgreSQL has a healthcheck
- Backup and restore scripts exist, are executable, and follow safety conventions
