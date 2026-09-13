#!/usr/bin/env bash
set -euo pipefail

readonly target="${1:-${XDG_CONFIG_HOME:-$HOME/.config}/tuck/tuck.env}"

if [[ -e "$target" || -L "$target" ]]; then
  echo "Production environment already exists: $target" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate the database password" >&2
  exit 1
fi

umask 077
mkdir -p "$(dirname "$target")"
readonly password="$(openssl rand -hex 32)"
readonly temporary="$(mktemp "${target}.tmp.XXXXXX")"
trap 'rm -f "$temporary"' EXIT

{
  printf 'POSTGRES_USER=tuck\n'
  printf 'POSTGRES_PASSWORD=%s\n' "$password"
  printf 'POSTGRES_DB=tuck\n'
  printf 'POSTGRES_PORT=%s\n' "${TUCK_POSTGRES_PORT:-5432}"
  printf 'TUCK_COMPOSE_DATABASE_URL=postgresql+asyncpg://tuck:%s@postgres:5432/tuck\n' "$password"
  printf 'TUCK_ENVIRONMENT=production\n'
  printf 'API_PORT=%s\n' "${TUCK_API_PORT:-8180}"
  printf 'WEB_PORT=%s\n' "${TUCK_WEB_PORT:-8181}"
} >"$temporary"

chmod 600 "$temporary"
if ! ln -T -- "$temporary" "$target"; then
  echo "Production environment already exists: $target" >&2
  exit 1
fi
rm -f "$temporary"
trap - EXIT
printf 'Created production environment at %s\n' "$target"
