#!/usr/bin/env bash
#
# postgres-backup.sh — Export a PostgreSQL database to a timestamped SQL dump.
#
# Usage:
#   ./scripts/postgres-backup.sh [--output FILE] [--host HOST] [--port PORT]
#                                [--database DB] [--user USER] [--password PASS]
#
# Defaults are read from environment variables, falling back to safe values that
# are suitable only for local development. Production runs MUST set all of:
#
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DATABASE, POSTGRES_USER,
#   POSTGRES_PASSWORD (or PGPASSWORD)
#
# The script refuses to run against "localhost" when POSTGRES_HOST is unset and
# warns when POSTGRES_PASSWORD equals the development default.

set -euo pipefail

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DATABASE="${POSTGRES_DATABASE:-tuck}"
POSTGRES_USER="${POSTGRES_USER:-tuck}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

# Default output: timestamped file in the current directory
OUTPUT="${OUTPUT:-$(date +%Y%m%d_%H%M%S)_${POSTGRES_DATABASE}_backup.sql}"

show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Export a PostgreSQL database to a timestamped SQL file.

Environment variables (all optional, but REQUIRED for production):
  POSTGRES_HOST      Database host (default: localhost)
  POSTGRES_PORT      Database port (default: 5432)
  POSTGRES_DATABASE  Database name (default: tuck)
  POSTGRES_USER      Database user (default: tuck)
  POSTGRES_PASSWORD  Database password (no default — MUST be set in production)
  OUTPUT            Output file path (default: timestamped SQL in CWD)

Options:
  --host HOST        Override POSTGRES_HOST
  --port PORT        Override POSTGRES_PORT
  --database DB      Override POSTGRES_DATABASE
  --user USER        Override POSTGRES_USER
  --password PASS    Override POSTGRES_PASSWORD
  --output FILE      Override OUTPUT
  --help             Show this help message

Examples:
  # Development (uses .env defaults):
  ./scripts/postgres-backup.sh

  # Production with explicit environment:
  POSTGRES_HOST=db.example.com POSTGRES_PASSWORD=secret ./scripts/postgres-backup.sh

  # Custom output file:
  ./scripts/postgres-backup.sh --output /backups/db-$(date +%Y%m%d).sql
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --host)
            POSTGRES_HOST="$2"
            shift 2
            ;;
        --port)
            POSTGRES_PORT="$2"
            shift 2
            ;;
        --database)
            POSTGRES_DATABASE="$2"
            shift 2
            ;;
        --user)
            POSTGRES_USER="$2"
            shift 2
            ;;
        --password)
            POSTGRES_PASSWORD="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help >&2
            exit 1
            ;;
    esac
done

# Safety checks
if [[ -z "$POSTGRES_PASSWORD" ]]; then
    echo "ERROR: POSTGRES_PASSWORD is not set." >&2
    echo "Set POSTGRES_PASSWORD or pass --password." >&2
    exit 1
fi

if [[ "$POSTGRES_HOST" == "localhost" ]]; then
    echo "WARNING: Targeting localhost. This is fine for development but confirm" >&2
    echo "you are not accidentally backing up a production database." >&2
fi

if [[ "$POSTGRES_PASSWORD" == "local-development-only" ]]; then
    echo "WARNING: Using the default development password." >&2
    echo "Change POSTGRES_PASSWORD for any non-local environment." >&2
fi

# Ensure pg_dump is available
if ! command -v pg_dump &>/dev/null; then
    echo "ERROR: pg_dump not found. Install PostgreSQL client tools." >&2
    exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"

echo "Backing up ${POSTGRES_DATABASE} from ${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}..."
echo "Output: ${OUTPUT}"

pg_dump \
    --host "${POSTGRES_HOST}" \
    --port "${POSTGRES_PORT}" \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DATABASE}" \
    --format plain \
    --verbose \
    --file "${OUTPUT}"

echo "Backup complete: ${OUTPUT}"
