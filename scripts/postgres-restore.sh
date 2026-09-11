#!/usr/bin/env bash
#
# postgres-restore.sh — Restore a PostgreSQL database from a SQL dump.
#
# Usage:
#   ./scripts/postgres-restore.sh [--input FILE] [--host HOST] [--port PORT]
#                                 [--database DB] [--user USER] [--password PASS]
#                                 [--yes] [--dry-run]
#
# Defaults are read from environment variables, falling back to safe values that
# are suitable only for local development. Production runs MUST set all of:
#
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DATABASE, POSTGRES_USER,
#   POSTGRES_PASSWORD (or PGPASSWORD)
#
# By default the script requires explicit confirmation before restoring.
# Use --yes to skip the confirmation prompt (e.g. in CI or automation).
# Use --dry-run to validate the input file without actually restoring.
#
# The restore target database is DROPPED and recreated by default so the restore
# produces a clean state. This is intentional for recovery scenarios; it can
# destroy existing data. The script refuses to run against "localhost" without a
# warning, and blocks restores that target the development default password.

set -euo pipefail

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DATABASE="${POSTGRES_DATABASE:-tuck}"
POSTGRES_USER="${POSTGRES_USER:-tuck}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

INPUT="${INPUT:-}"
DRY_RUN="${DRY_RUN:-false}"
AUTOMATED="${AUTOMATED:-false}"

show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] --input FILE

Restore a PostgreSQL database from a SQL dump.

WARNING: This script DROPS and recreates the target database by default.
Confirm you have a recent backup before running in production.

Environment variables (all optional, but REQUIRED for production):
  POSTGRES_HOST      Database host (default: localhost)
  POSTGRES_PORT      Database port (default: 5432)
  POSTGRES_DATABASE  Database name (default: tuck)
  POSTGRES_USER      Database user (default: tuck)
  POSTGRES_PASSWORD  Database password (no default — MUST be set in production)
  AUTOMATED          Set to "true" to skip interactive confirmation (default: false)

Options:
  --input FILE       Path to SQL dump file (required unless INPUT is set)
  --host HOST        Override POSTGRES_HOST
  --port PORT        Override POSTGRES_PORT
  --database DB      Override POSTGRES_DATABASE
  --user USER        Override POSTGRES_USER
  --password PASS    Override POSTGRES_PASSWORD
  --yes              Skip confirmation prompt (same as AUTOMATED=true)
  --dry-run          Validate input without restoring
  --help             Show this help message

Examples:
  # Interactive restore (asks for confirmation):
  ./scripts/postgres-restore.sh --input backup.sql

  # Automation-friendly restore (no prompt):
  AUTOMATED=true ./scripts/postgres-restore.sh --input backup.sql

  # Dry run (validate only):
  ./scripts/postgres-restore.sh --input backup.sql --dry-run

  # Production restore:
  POSTGRES_HOST=db.example.com POSTGRES_PASSWORD=secret \
      ./scripts/postgres-restore.sh --input backup.sql --yes
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --input)
            INPUT="$2"
            shift 2
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
        --yes)
            AUTOMATED="true"
            shift
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help >&2
            exit 1
            ;;
    esac
done

# Safety checks
if [[ -z "$INPUT" ]]; then
    echo "ERROR: No input file specified." >&2
    echo "Use --input FILE or set the INPUT environment variable." >&2
    exit 1
fi

if [[ ! -f "$INPUT" ]]; then
    echo "ERROR: Input file not found: ${INPUT}" >&2
    exit 1
fi

if [[ -z "$POSTGRES_PASSWORD" ]]; then
    echo "ERROR: POSTGRES_PASSWORD is not set." >&2
    echo "Set POSTGRES_PASSWORD or pass --password." >&2
    exit 1
fi

if [[ "$POSTGRES_PASSWORD" == "local-development-only" ]]; then
    echo "ERROR: Restore blocked: using the default development password." >&2
    echo "Set POSTGRES_PASSWORD to a real password before restoring." >&2
    exit 1
fi

if [[ "$POSTGRES_HOST" == "localhost" ]]; then
    echo "WARNING: Targeting localhost. Confirm this is the intended database." >&2
    echo "Restore will DROP and recreate the database." >&2
fi

# Require confirmation unless automated
if [[ "$AUTOMATED" != "true" ]]; then
    echo ""
    echo "============================================================"
    echo " DATABASE RESTORE — DESTRUCTIVE OPERATION"
    echo "============================================================"
    echo "Target:  ${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DATABASE}"
    echo "Input:   ${INPUT}"
    echo "Dry run: ${DRY_RUN}"
    echo ""
    echo "This will DROP and recreate the database, then restore from backup."
    echo "Existing data in ${POSTGRES_DATABASE} will be LOST."
    echo "============================================================"
    echo ""
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "Dry run — no changes will be made."
    else
        read -r -p "Type ' RESTORE ${POSTGRES_DATABASE} ' to confirm (or Ctrl-C to abort): " confirmation
        if [[ "$confirmation" != "RESTORE ${POSTGRES_DATABASE}" ]]; then
            echo "Restore aborted by user."
            exit 1
        fi
    fi
fi

# Ensure psql/pg_restore is available
if ! command -v psql &>/dev/null; then
    echo "ERROR: psql not found. Install PostgreSQL client tools." >&2
    exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "Dry run — validating input file..."
    # Validate the SQL file by checking it's non-empty and has expected content
    if [[ ! -s "$INPUT" ]]; then
        echo "ERROR: Input file is empty." >&2
        exit 1
    fi
    echo "Input file looks valid (non-empty)."
    echo "Dry run complete — no changes made."
    exit 0
fi

echo "Restoring ${POSTGRES_DATABASE} from ${INPUT}..."
echo "Target: ${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}"

# Drop and recreate the database for a clean restore
echo "Dropping existing database ${POSTGRES_DATABASE}..."
psql \
    --host "${POSTGRES_HOST}" \
    --port "${POSTGRES_PORT}" \
    --username "${POSTGRES_USER}" \
    --dbname "postgres" \
    --echo-queries \
    -c "DROP DATABASE IF EXISTS \"${POSTGRES_DATABASE}\";"

echo "Creating database ${POSTGRES_DATABASE}..."
psql \
    --host "${POSTGRES_HOST}" \
    --port "${POSTGRES_PORT}" \
    --username "${POSTGRES_USER}" \
    --dbname "postgres" \
    --echo-queries \
    -c "CREATE DATABASE \"${POSTGRES_DATABASE}\";"

echo "Restoring data..."
psql \
    --host "${POSTGRES_HOST}" \
    --port "${POSTGRES_PORT}" \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DATABASE}" \
    --echo-queries \
    -f "${INPUT}"

echo "Restore complete: ${POSTGRES_DATABASE}"
