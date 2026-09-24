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

## Phase 3 command workflow

The authenticated PWA sends natural-language text to `POST /api/v1/captures/text`. The API stores
the raw capture before invoking the LangGraph workflow. Every request needs a caller-generated
`source_request_id`; repeating the same ID for the same user and source returns the original receipt
without creating another resource.

The first interpreter is the deterministic, provider-neutral `RuleBasedInterpreter`. It supports
the representative creation forms in `backend/tests/fixtures/command_evaluations.json` while the
model provider and privacy budget remain an explicit architecture decision. Unsupported,
destructive, or ambiguous text enters the review inbox instead of being guessed. The interpreter
can later be replaced behind the `CommandInterpreter` protocol without changing persistence,
policy, domain tools, or API responses.

Run the fast schema and evaluation tests with:

```bash
cd backend
uv run pytest tests/test_command_schemas.py tests/test_command_interpreter.py \
  tests/test_command_evaluations.py
```
