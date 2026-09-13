# Tuck Deployment

## Overview

Tuck runs as four containerized services on a single host inside the home tailnet:

- **PostgreSQL 17** — application database
- **FastAPI** — REST API and business logic
- **Reminder worker** — durable Web Push delivery
- **nginx** — static PWA assets plus API proxy

The compose file at the repository root defines all four services and is the single source of truth for the container layout. Read that file first when changing the deployment.

## Prerequisites

- Docker (or Podman + podman-compose) on the host
- Tailscale client authenticated and present on the host
- Tailscale Serve enabled for the HTTP port you want to expose
- A Tailnet machine (e.g. `fedora-1`) that is always on and reachable from the tailnet
- A repository administrator who can create a short-lived self-hosted runner
  registration token

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

Built from `backend/Dockerfile`. Connects to PostgreSQL using the `TUCK_DATABASE_URL` application setting. Compose populates it from `TUCK_COMPOSE_DATABASE_URL` so production can provide a complete, correctly URL-encoded DSN.

On startup the container:

1. Runs `alembic upgrade head` to apply any pending migrations.
2. Starts `uvicorn tuck_api.main:app` on port 8000.

Health endpoints:

- `GET /api/v1/health` — liveness, no dependency on database
- `GET /api/v1/ready` — readiness, validates configuration; returns 503 if invalid

Liveness and readiness should be monitored by the host orchestrator. The compose healthcheck queries `/api/v1/health`.

### Reminder worker

Built from the backend image and started with `tuck-reminder-worker`. The worker materializes due deliveries, claims a bounded batch, sends Web Push, records outcomes, and retries transient failures with bounded backoff. PostgreSQL is the scheduling source of truth, so a worker restart does not lose due work; expired claims become eligible after the configured lease.

The worker healthcheck runs `tuck-reminder-worker --health-check`. It validates the complete VAPID configuration and executes `SELECT 1` against PostgreSQL. The worker needs outbound DNS and HTTPS on TCP port 443 to the browser push-provider URLs stored in active subscriptions. It needs no public inbound port.

### Web (nginx)

Built from `frontend/Dockerfile` as a multi-stage image. Node and pnpm build the PWA, then `nginx:alpine` serves the resulting assets and proxies `/api/` requests to the FastAPI service.

The nginx configuration lives at `docker/web/nginx.conf` and is copied into the runtime image during the build.

## Secrets and configuration

All configuration is supplied through environment variables. The repository ships a `.env.example` with safe non-production defaults. Copy it to `.env` and adjust for your environment.

**Production secrets that MUST NOT be committed:**

- `POSTGRES_PASSWORD`
- `TUCK_COMPOSE_DATABASE_URL`
- `TUCK_VAPID_PUBLIC_KEY`
- `TUCK_VAPID_PRIVATE_KEY`
- `TUCK_VAPID_SUBJECT` (`mailto:` or `https:` contact URI)
- Any real hostnames, tailnet identifiers, or credentials

The compose file reads these from the host environment or `.env` file. For production deployments, consider one of:

- A host-level `.env` file with restricted permissions (`chmod 600 .env`)
- Docker secrets if running in swarm mode
- An external secret manager integrated through the environment

The `.env.example` file is the template. The `.env` file is `.gitignore`d and must never be committed.

Generate one P-256 VAPID key pair in a protected directory, using the backend project only to supply the tool:

```bash
cd /protected/path
uv run --project /path/to/tuck/repo/backend vapid --gen
uv run --project /path/to/tuck/repo/backend vapid \
  --applicationServerKey --private-key /protected/path/private_key.pem
```

Store the reported browser-facing value as `TUCK_VAPID_PUBLIC_KEY`, the private PEM as the single-quoted multiline `TUCK_VAPID_PRIVATE_KEY` value, and an operator contact URI as `TUCK_VAPID_SUBJECT`. Never generate or store the PEM files inside the repository.

Rotate VAPID keys as one change: generate a new pair, update all three settings in the protected production environment, rebuild/recreate `api` and `reminder-worker`, and confirm both API readiness and worker health. Browsers must disable and re-enable notifications after rotation so subscriptions are recreated with the new public key. Keep the prior private key only until that resubscription window ends, then destroy it according to the secret-retention policy.

## Startup sequence and migrations

The API service depends on PostgreSQL and waits for the `service_healthy` condition before starting. During startup the API container runs Alembic migrations before the application server starts.

This means:

- First startup creates the schema automatically.
- Subsequent startups apply any new migrations from the `backend/migrations` directory.
- Migrations run as part of the container entrypoint; they are not separate manual steps.

If a migration fails, the API container exits. Check logs with `docker compose logs api`.

## Health checks

| Service         | Healthcheck  | Endpoint/command                      |
| --------------- | ------------ | ------------------------------------- |
| postgres        | `pg_isready` | Direct PostgreSQL check               |
| api             | HTTP GET     | `/api/v1/health`                      |
| reminder-worker | CLI          | `tuck-reminder-worker --health-check` |
| web             | HTTP GET     | `/` (nginx returns 200)               |

The API also exposes `/api/v1/ready` for deeper readiness probing. A full operational probe should check both:

1. `GET /api/v1/health` → 200
2. `GET /api/v1/ready` → 200

## Logs

All services log to stdout/stderr, captured by the container runtime. Use:

```bash
docker compose logs -f          # all services
docker compose logs -f api      # API only
docker compose logs -f reminder-worker
docker compose logs -f postgres # PostgreSQL only
```

Compose is configured with rotated json-file logging (10 MB max, 3 files) to avoid unbounded disk growth.

## GitHub Actions CI and deployment

`.github/workflows/deploy.yml` runs for pull requests and pushes to `main`. The CI job uses locked dependencies and runs Ruff formatting/linting, mypy, pytest against PostgreSQL 17, Prettier, ESLint, TypeScript checks, Vitest, Playwright, the production frontend build, and all deployment image builds.

After CI succeeds on `main`, the deployment job runs on the production host.
The job requires a GitHub Actions self-hosted runner with the default `Linux`
and `X64` labels plus the custom `tuck-production` label. If no matching runner
is online, GitHub leaves the job queued and eventually cancels it without
executing any deployment step.

### One-time production-host bootstrap

Create the production environment as the unprivileged account that will run
deployments:

```bash
TUCK_VAPID_SUBJECT=mailto:operator@example.com scripts/create-production-env.sh
scripts/validate-production-config.sh "$HOME/.config/tuck/tuck.env"
```

The bootstrap creates `$HOME/.config/tuck/tuck.env` with mode `0600`, a random
database password, a fresh VAPID key pair, production mode, and host ports
`8180` (API) and `8181` (web). Set `TUCK_VAPID_SUBJECT` to a real operator
contact URI. The script refuses to overwrite an existing file. Override the
ports only when necessary by setting `TUCK_API_PORT` or `TUCK_WEB_PORT` before
running it.

Next, a repository administrator creates a short-lived registration token in
**Settings → Actions → Runners → New self-hosted runner**. On the production
host, pass that token through the environment rather than storing it in a
file or shell script:

```bash
read -rsp "Runner registration token: " TUCK_RUNNER_REGISTRATION_TOKEN
export TUCK_RUNNER_REGISTRATION_TOKEN
scripts/install-production-runner.sh \
  https://github.com/OWNER/REPOSITORY
unset TUCK_RUNNER_REGISTRATION_TOKEN
```

The installer downloads a pinned runner release, verifies its SHA-256 digest,
registers it with `tuck-production`, and enables the
`tuck-actions-runner.service` user unit. The deployment account must have
permission to use the host's Docker-compatible Compose installation. User
lingering must be enabled so the service remains active without an interactive
login (`loginctl show-user "$USER" -p Linger`).

By default, the workflow reads the runner-owned config at
`$HOME/.config/tuck/tuck.env`. Set the repository variable `TUCK_ENV_FILE` to
an absolute path if the host uses a different location. The file must define
the PostgreSQL values, a complete `TUCK_COMPOSE_DATABASE_URL` using the
internal `postgres:5432` address, `TUCK_ENVIRONMENT=production`, and the
complete VAPID settings; it must never be committed. The workflow rejects
development defaults or missing VAPID values. Protect the GitHub `production`
environment if deployment approval is desired.

Verify the runner before merging a deployment change:

```bash
systemctl --user status tuck-actions-runner.service
```

The deployment job rebuilds the backend and web images from the verified revision, starts the Compose project (which applies Alembic migrations before Uvicorn), waits for the reminder-worker healthcheck, and verifies `/api/v1/ready` from inside the API container. GitHub Actions serializes deployments so two revisions cannot update the host concurrently.

## Manual update sequence

To update Tuck to a new version:

```bash
# 1. Pull or check out the desired code
git pull   # or checkout a tagged release

# 2. Rebuild application images
docker compose build api reminder-worker web

# 3. Recreate the services
docker compose up -d

# 4. Watch the startup logs for migration status
docker compose logs -f api
```

The API container always runs migrations on startup, so schema changes are applied automatically when the new image starts.

## Backup and restore

See `scripts/postgres-backup.sh` and `scripts/postgres-restore.sh` for the backup/restore tooling. A full database dump includes `push_subscriptions`, `reminder_recipients`, and `notification_deliveries`; restoring only the older tables leaves Phase 2 scheduling incomplete. Those scripts and restore verification are documented in the Operator Runbook.

## Testing the deployment

The repository has tests that validate the deployment configuration:

```bash
cd backend
uv run pytest tests/test_deployment.py tests/test_backup_restore.py -v
```

These tests check:

- compose.yaml parses without errors
- All required services are defined (postgres, api, reminder-worker, web)
- PostgreSQL has a healthcheck
- Production configuration rejects development defaults and invalid internal database URLs
- Backup and restore scripts exist, are executable, and follow safety conventions
- A real PostgreSQL dump/restore round trip preserves the Phase 2 notification tables
