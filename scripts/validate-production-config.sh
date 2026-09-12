#!/usr/bin/env bash
set -euo pipefail

readonly env_file="${1:-}"
if [[ -z "$env_file" || ! -r "$env_file" ]]; then
  echo "Usage: $0 /absolute/path/to/readable-production.env" >&2
  exit 1
fi

rendered="$(docker compose --env-file "$env_file" config)"
if [[ "$rendered" == *"local-development-only"* ]]; then
  echo "Production configuration uses the development database password" >&2
  exit 1
fi
if [[ "$rendered" != *"TUCK_ENVIRONMENT: production"* ]]; then
  echo "TUCK_ENVIRONMENT must be production" >&2
  exit 1
fi
if [[ "$rendered" != *"@postgres:5432/"* ]]; then
  echo "TUCK_COMPOSE_DATABASE_URL must use the internal postgres:5432 address" >&2
  exit 1
fi
for setting in TUCK_VAPID_PUBLIC_KEY TUCK_VAPID_PRIVATE_KEY TUCK_VAPID_SUBJECT; do
  if [[ "$rendered" != *"${setting}:"* || "$rendered" == *"${setting}: null"* || "$rendered" == *"${setting}: ''"* || "$rendered" == *"${setting}: \"\""* ]]; then
    echo "VAPID settings must all be non-empty" >&2
    exit 1
  fi
done
