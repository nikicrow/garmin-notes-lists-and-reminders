# Tuck Operator Runbook

## Scope

This runbook covers routine operation of Tuck on a single host inside the home tailnet. It assumes:
- The host is authenticated to Tailscale and reachable from the tailnet.
- The Tuck repository is deployed from a tagged or pinned release.
- Services run via `docker compose` (or `podman-compose`) from the repository root.

**Do not store private hostnames, tailnet node names, production credentials, or Tailscale auth material in this file or anywhere in the repository.** Replace any example hostnames with your actual values at deployment time, outside the repo.

## System overview

Tuck is three containers:

- `postgres` — PostgreSQL 17, holds all application data
- `api` — FastAPI service, depends on postgres, runs migrations on startup
- `web` — nginx, serves the PWA and proxies `/api/` to the `api` container

All three are defined in `compose.yaml`. The repo root `compose.yaml` is the single source of truth.

## Prerequisites for operation

- The host has Docker or Podman with compose support available.
- Tailscale is running on the host and the host is reachable from the tailnet.
- You have console or SSH access to the host.
- You have the Tuck repository checked out at the version you want to run.
- You have a `.env` file (or equivalent environment) with the required secrets.

## Required secrets

These must be set before starting services. They are NOT in the repository:

- `POSTGRES_PASSWORD` — PostgreSQL superuser password
- `TUCK_COMPOSE_DATABASE_URL` — complete URL-encoded asyncpg DSN using `postgres:5432`
- `TUCK_ENVIRONMENT=production`
- `POSTGRES_USER`, `POSTGRES_DB` — usually left at defaults (`tuck`)
- `POSTGRES_PORT` — usually left at default (`5432`)
- `API_PORT` — internal API port (default `8000`)
- `WEB_PORT` — internal web port (default `8080`)

Copy `.env.example` to `.env` and fill in real values. Protect the `.env` file with restricted permissions:

```bash
cp .env.example .env
chmod 600 .env
# Edit .env with real values — do not commit it
```

For production, prefer a secret manager or Docker secrets over a plain `.env` file.

## Starting Tuck

From the repository root:

```bash
docker compose up -d
```

This starts all three services. The API waits for PostgreSQL to become healthy, then runs migrations and starts the application server.

To watch startup progress:

```bash
docker compose logs -f api
```

Look for:
- `Running database migrations...`
- `Starting application server...`
- No error messages

## Checking the system is healthy

### Quick status

```bash
docker compose ps
```

All three services should show `healthy` in the `Status` column once started.

### Liveness and readiness

The API exposes two endpoints:

- `GET /api/v1/health` — liveness. Should return `200` with `{"status": "ok"}`. Does not depend on database.
- `GET /api/v1/ready` — readiness. Should return `200` with `{"status": "ready"}`. Validates configuration.

Example probe:

```bash
# From the host or any tailnet machine
curl -fsS http://<host-ip>:8000/api/v1/health
curl -fsS http://<host-ip>:8000/api/v1/ready
```

Replace `<host-ip>` with the host's tailnet IP or reachable address. The `web` service proxies `/api/` to the API, so you can also check through the web port if nginx is configured to proxy.

### Service-specific checks

```bash
# PostgreSQL
docker compose ps postgres
docker compose logs postgres | tail -20

# API
docker compose ps api
docker compose logs api | tail -30

# Web
docker compose ps web
docker compose logs web | tail -20
```

## Updating Tuck

### Update the code

```bash
# Option A: pull the latest tagged release
git fetch --tags
git checkout <tag>

# Option B: use a specific commit
git checkout <commit>
```

### Rebuild the API image

If the backend code changed (Python files, dependencies, migrations):

```bash
docker compose build api
```

If only frontend assets changed, rebuild the frontend and restart `web`:

```bash
cd frontend
pnpm install
pnpm build
cd ..
docker compose up -d web
```

### Restart services

```bash
docker compose up -d
```

The API will run any new migrations on startup. Watch the logs to confirm:

```bash
docker compose logs -f api
```

## Backup

Use the backup script at `scripts/postgres-backup.sh`. It creates a timestamped SQL dump.

### Basic backup

```bash
# Set environment variables for the target database
export POSTGRES_HOST=<postgres-host>
export POSTGRES_PORT=5432
export POSTGRES_DATABASE=tuck
export POSTGRES_USER=tuck
export POSTGRES_PASSWORD=<real-password>

./scripts/postgres-backup.sh
```

The script writes a file like `20260906_120000_tuck_backup.sql` in the current directory.

### Backup with explicit options

```bash
./scripts/postgres-backup.sh \
    --host <postgres-host> \
    --port 5432 \
    --database tuck \
    --user tuck \
    --password <real-password> \
    --output /backups/tuck_$(date +%Y%m%d).sql
```

### Backup from the compose environment

If PostgreSQL is running in compose and you want to back it up from the host:

```bash
# Point POSTGRES_HOST at the compose postgres service
# For local compose, use the mapped host port (default 5432)
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DATABASE=tuck
export POSTGRES_USER=tuck
export POSTGRES_PASSWORD=<real-password>

./scripts/postgres-backup.sh --output ./backups/tuck_$(date +%Y%m%d_%H%M%S).sql
```

Store backups outside the compose volumes, on a separate disk or backup target.

### Automated backups

For recurring backups, schedule the backup script with your preferred scheduler (cron, systemd timer, etc.). Example cron entry (run as a user with access to the database):

```bash
# Backup daily at 2 AM, keep the last 30 days
0 2 * * * cd /path/to/tuck && \
    POSTGRES_HOST=localhost POSTGRES_PASSWORD=<real-password> \
    ./scripts/postgres-backup.sh \
    --output /backups/tuck_$(date +\%Y\%m\%d_\%H\%M\%S).sql
```

Rotate old backups separately with your retention policy. The backup script itself does not delete old backups.

## Restore

Use the restore script at `scripts/postgres-restore.sh`. It restores a SQL dump into a fresh database.

### Before restoring

- Confirm you have a recent backup.
- Confirm you understand that the restore script DROPS and recreates the target database.
- Notify users if applicable.

### Dry run

Always do a dry run first to validate the backup file:

```bash
export POSTGRES_HOST=<target-host>
export POSTGRES_PASSWORD=<real-password>

./scripts/postgres-restore.sh --input /path/to/backup.sql --dry-run
```

A dry run validates the file without making changes.

### Full restore

```bash
export POSTGRES_HOST=<target-host>
export POSTGRES_PORT=5432
export POSTGRES_DATABASE=tuck
export POSTGRES_USER=tuck
export POSTGRES_PASSWORD=<real-password>

./scripts/postgres-restore.sh --input /path/to/backup.sql --yes
```

The `--yes` flag skips the interactive confirmation prompt. For interactive use, omit `--yes` and the script will ask you to type the database name to confirm.

### Restore safety rules

- The restore script blocks if `POSTGRES_PASSWORD` is unset or equals the development default.
- The restore script warns when targeting `localhost`.
- The restore script requires confirmation (or `--yes`) before proceeding.
- The restore script drops and recreates the target database.

### Restore to a different database name

To restore to a different database (e.g. for verification before switching over):

```bash
export POSTGRES_DATABASE=tuck_restored
./scripts/postgres-restore.sh --input /path/to/backup.sql --yes
```

Then verify the restored data before switching application configuration to point at `tuck_restored`.

## Disaster recovery checklist

If the system is down or data is lost:

1. **Stop writes.** Prevent further changes while diagnosing.
   ```bash
   docker compose down
   ```

2. **Assess what failed.**
   ```bash
   docker compose ps
   docker compose logs postgres
   docker compose logs api
   docker compose logs web
   df -h   # check disk space
   ```

3. **If PostgreSQL is broken but the volume is intact**, try restarting:
   ```bash
   docker compose up -d postgres
   docker compose logs -f postgres
   ```

4. **If data is corrupted or lost**, restore from the latest backup:
   ```bash
   ./scripts/postgres-restore.sh --input /path/to/latest/backup.sql --yes
   ```

5. **If the volume is lost**, rebuild and restore:
   ```bash
   docker compose down --volumes   # WARNING: destroys all local data
   docker compose up -d postgres
   # Wait for postgres to be healthy, then:
   ./scripts/postgres-restore.sh --input /path/to/latest/backup.sql --yes
   docker compose up -d
   ```

6. **Verify the restore.**
   - Check that all three services are healthy: `docker compose ps`
   - Check that the API responds: `curl -fsS http://<host>:8000/api/v1/health`
   - Log in and verify recent data is present.

7. **Resume normal operation.**

## Common issues

### API fails to start, migration error

Check migration logs:
```bash
docker compose logs api
```

Common causes:
- PostgreSQL not ready yet — wait and retry.
- Migration file missing or corrupted — verify the code checkout.
- Database connection refused — check network and credentials.

### Database connection refused

Check that PostgreSQL is healthy:
```bash
docker compose ps postgres
docker compose logs postgres
```

If PostgreSQL is not healthy, wait a few seconds and check again. If it stays unhealthy, inspect logs.

### Web service returns 502 for API calls

The web container proxies `/api/` to the `api` container. If the API is down or not yet started, nginx returns 502.

Check:
```bash
docker compose ps api
docker compose logs api
```

### Disk full

Check disk usage:
```bash
df -h
docker system df
```

If disk is full:
- Clean old backups.
- Prune unused images: `docker image prune -f`
- Prune stopped containers: `docker container prune -f`
- Check postgres logs for clues.

### Backup script cannot connect

Verify the target database is reachable:
```bash
psql -h <host> -p <port> -U <user> -d <database> -c "SELECT 1;"
```

Ensure `pg_dump` is installed on the host running the backup script.

## Tailscale exposure

Tuck runs inside the tailnet. Expose it to tailnet devices through Tailscale Serve, not through public ports.

The compose file binds service ports to `127.0.0.1` by default. To expose to the tailnet:

1. Ensure Tailscale Serve is configured to forward the desired port to the local service.
2. Use the tailnet hostname or IP to reach Tuck from tailnet devices.
3. Do NOT expose the service publicly unless a specific integration requires it and you have reviewed the security implications.

## Port mapping reference

Default internal ports:
- PostgreSQL: 5432
- API: 8000
- Web: 8080

These are mapped to the host on `127.0.0.1` by default. Adjust `POSTGRES_PORT`, `API_PORT`, and `WEB_PORT` in `.env` to change the host-side ports.

The container-internal ports are fixed by the compose file and Dockerfile. Do not change them without updating all dependent configuration.

## Monitoring suggestions

Minimum viable monitoring:
- Service health: `docker compose ps` shows health status.
- Disk space: alert before disk fills.
- Backup freshness: alert if the latest backup is older than expected.
- API responsiveness: probe `GET /api/v1/health` and `GET /api/v1/ready` regularly.

## Support notes for this repository

- The deployment configuration lives in `compose.yaml`.
- The backend image is built from `backend/Dockerfile`.
- The web nginx configuration is in `docker/web/nginx.conf`.
- Backup and restore scripts are in `scripts/`.
- Tests that validate the deployment config are in `backend/tests/test_deployment.py` and `backend/tests/test_backup_restore.py`.

## When to get help

- If you are unsure whether a restore will destroy data you need, stop and verify the backup first.
- If the database volume is corrupted and there is no viable backup, stop and assess before attempting repairs.
- If you suspect a security incident, preserve logs and isolate the host before making changes.
