# Development

## Local PostgreSQL

Copy the safe example environment and start PostgreSQL from the repository root:

```bash
cp .env.example .env
docker compose up -d postgres
docker compose ps
```

The database port binds only to localhost. Compose reports the service healthy only after
`pg_isready` accepts connections. `GET /api/v1/health` is a liveness check that does not depend on
configuration or PostgreSQL. `GET /api/v1/ready` validates application settings and reports ready;
it returns `503 Service Unavailable` when configuration is missing or invalid. Database connectivity
will become part of that probe when persistence is wired.

Stop the service with `docker compose down`. Add `--volumes` only when the local development data
should be deleted.

## Isolated test databases

Settings and unit tests do not connect to PostgreSQL. Database integration tests must never use the
`tuck` development database. Each test process must create a uniquely named temporary database from
an administrator connection, run all migrations against it, and drop it during teardown. CI follows
the same create-migrate-test-drop lifecycle. A failed run may leave only its uniquely named test
database, which can be identified and removed without risking development data.
