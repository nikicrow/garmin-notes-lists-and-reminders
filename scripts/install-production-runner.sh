#!/usr/bin/env bash
set -euo pipefail

readonly RUNNER_VERSION="2.337.0"
readonly RUNNER_SHA256="70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613"
readonly ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
readonly DOWNLOAD_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ARCHIVE}"
readonly repository_url="${1:-}"
readonly install_dir="${TUCK_RUNNER_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/tuck-actions-runner}"
readonly unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
readonly unit_file="$unit_dir/tuck-actions-runner.service"
readonly registration_token="${TUCK_RUNNER_REGISTRATION_TOKEN:-}"
unset TUCK_RUNNER_REGISTRATION_TOKEN

usage() {
  cat <<'EOF'
Usage:
  TUCK_RUNNER_REGISTRATION_TOKEN=<token> \
    scripts/install-production-runner.sh https://github.com/OWNER/REPOSITORY

The token is a short-lived repository runner registration token obtained by a
repository administrator. The runner is installed for the current user and is
registered with the required tuck-production label.
EOF
}

if [[ "$repository_url" == "--help" || "$repository_url" == "-h" ]]; then
  usage
  exit 0
fi
if [[ -z "$repository_url" || "$repository_url" != https://github.com/*/* ]]; then
  usage >&2
  exit 2
fi
if [[ -z "$registration_token" ]]; then
  echo "TUCK_RUNNER_REGISTRATION_TOKEN is required" >&2
  exit 2
fi
if [[ $EUID -eq 0 ]]; then
  echo "Run this installer as the unprivileged deployment account, not root" >&2
  exit 1
fi
if [[ -e "$install_dir/.runner" ]]; then
  echo "A runner is already configured at $install_dir" >&2
  exit 1
fi
for command in curl id loginctl sha256sum tar systemctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required" >&2
    exit 1
  fi
done
readonly runner_user="$(id -un)"
if [[ "$(loginctl show-user "$runner_user" -p Linger --value)" != "yes" ]]; then
  echo "User lingering is disabled; the runner would stop after logout." >&2
  echo "Enable it with: sudo loginctl enable-linger $runner_user" >&2
  exit 1
fi

umask 077
mkdir -p "$install_dir" "$unit_dir"
readonly temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

curl --fail --location --silent --show-error \
  "$DOWNLOAD_URL" --output "$temporary/$ARCHIVE"
printf '%s  %s\n' "$RUNNER_SHA256" "$temporary/$ARCHIVE" | sha256sum --check --status
tar --extract --gzip --file "$temporary/$ARCHIVE" --directory "$install_dir"

(
  cd "$install_dir"
  ./config.sh \
    --unattended \
    --url "$repository_url" \
    --token "$registration_token" \
    --name "$(hostname)-tuck-production" \
    --labels "tuck-production" \
    --work "_work" \
    --replace
)

cat >"$unit_file" <<EOF
[Unit]
Description=Tuck GitHub Actions runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$install_dir
ExecStart=$install_dir/bin/runsvc.sh
Environment="PATH=%h/.local/bin:/usr/local/bin:/usr/bin"
Restart=on-failure
RestartSec=5
TimeoutStopSec=300

[Install]
WantedBy=default.target
EOF
chmod 600 "$unit_file"

systemctl --user daemon-reload
systemctl --user enable --now tuck-actions-runner.service
systemctl --user --no-pager --full status tuck-actions-runner.service
