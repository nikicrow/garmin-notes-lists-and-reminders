#!/usr/bin/env bash
set -euo pipefail

readonly target="${1:-${XDG_CONFIG_HOME:-$HOME/.config}/tuck/tuck.env}"
readonly vapid_subject="${TUCK_VAPID_SUBJECT:-}"

if [[ -e "$target" || -L "$target" ]]; then
  echo "Production environment already exists: $target" >&2
  exit 1
fi
if [[ "$vapid_subject" != mailto:* && "$vapid_subject" != https://* ]]; then
  echo "TUCK_VAPID_SUBJECT must start with mailto: or https://" >&2
  exit 1
fi
if [[ "$vapid_subject" == https://* ]]; then
  https_subject_authority="${vapid_subject#https://}"
  https_subject_authority="${https_subject_authority%%[/?#]*}"
  readonly https_subject_authority
  if [[ "$https_subject_authority" =~ ^[^:]+:[0-9]+$ || "$https_subject_authority" =~ ^\[[^]]+\]:[0-9]+$ ]]; then
    echo "HTTPS VAPID subject must not include a port" >&2
    exit 1
  fi
  if [[ ! "$vapid_subject" =~ ^https://(localhost|[[:alnum:]_-]+\.[[:alnum:]_.-]+|([[:xdigit:]]{1,4}:+)+[[:xdigit:]]{0,4})$ ]]; then
    echo "HTTPS VAPID subject is not compatible with py_vapid" >&2
    exit 1
  fi
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate the database password and VAPID keys" >&2
  exit 1
fi

umask 077
mkdir -p "$(dirname "$target")"
readonly password="$(openssl rand -hex 32)"
readonly temporary="$(mktemp "${target}.tmp.XXXXXX")"
readonly temporary_private_key="$(mktemp "${target}.vapid-private.XXXXXX")"
readonly temporary_public_key="$(mktemp "${target}.vapid-public.XXXXXX")"
trap 'rm -f "$temporary" "$temporary_private_key" "$temporary_public_key"' EXIT

openssl ecparam -name prime256v1 -genkey -noout -out "$temporary_private_key"
openssl ec \
  -in "$temporary_private_key" \
  -pubout \
  -conv_form uncompressed \
  -outform DER \
  -out "$temporary_public_key" \
  2>/dev/null
readonly public_key_size="$(stat -c %s "$temporary_public_key")"
if ((public_key_size < 65)); then
  echo "Generated VAPID public key has an unexpected format" >&2
  exit 1
fi
readonly vapid_public_key="$(
  dd \
    if="$temporary_public_key" \
    bs=1 \
    skip="$((public_key_size - 65))" \
    status=none |
    openssl base64 -A |
    tr '+/' '-_' |
    tr -d '='
)"
if ! vapid_private_key="$(
  openssl ec -in "$temporary_private_key" -outform DER 2>/dev/null |
    openssl base64 -A |
    tr '+/' '-_' |
    tr -d '='
)"; then
  echo "Failed to convert generated VAPID private key" >&2
  exit 1
fi
if [[ -z "$vapid_private_key" ]]; then
  echo "Generated VAPID private key is empty" >&2
  exit 1
fi
readonly vapid_private_key

{
  printf 'POSTGRES_USER=tuck\n'
  printf 'POSTGRES_PASSWORD=%s\n' "$password"
  printf 'POSTGRES_DB=tuck\n'
  printf 'POSTGRES_PORT=%s\n' "${TUCK_POSTGRES_PORT:-5432}"
  printf 'TUCK_COMPOSE_DATABASE_URL=postgresql+asyncpg://tuck:%s@postgres:5432/tuck\n' "$password"
  printf 'TUCK_ENVIRONMENT=production\n'
  printf 'TUCK_VAPID_PUBLIC_KEY=%s\n' "$vapid_public_key"
  printf 'TUCK_VAPID_PRIVATE_KEY=%s\n' "$vapid_private_key"
  printf 'TUCK_VAPID_SUBJECT=%s\n' "$vapid_subject"
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
rm -f "$temporary_private_key" "$temporary_public_key"
printf 'Created production environment at %s\n' "$target"
