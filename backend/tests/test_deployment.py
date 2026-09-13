"""Tests for deployment configuration."""

import os
import subprocess
from pathlib import Path

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PRODUCTION_CONFIG_VALIDATOR = os.path.join(_REPO_ROOT, "scripts", "validate-production-config.sh")


def _compose_cmd(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        os.path.join(_REPO_ROOT, "compose.yaml"),
        *args,
    ]


def test_compose_file_parses_without_errors() -> None:
    """Validate that compose.yaml is syntactically valid and can be parsed."""
    result = subprocess.run(
        _compose_cmd("config", "--quiet"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"compose.yaml failed to parse: {result.stderr}"


def test_compose_contains_postgres_service() -> None:
    """Validate that the compose file defines a PostgreSQL service."""
    result = subprocess.run(
        _compose_cmd("config", "--services"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    services = result.stdout.strip().split("\n")
    assert "postgres" in services


def test_compose_contains_api_service() -> None:
    """Validate that the compose file defines the FastAPI application service."""
    result = subprocess.run(
        _compose_cmd("config", "--services"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    services = result.stdout.strip().split("\n")
    assert "api" in services


def test_compose_contains_web_service() -> None:
    """Validate that the compose file defines the static web service."""
    result = subprocess.run(
        _compose_cmd("config", "--services"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    services = result.stdout.strip().split("\n")
    assert "web" in services


def test_compose_runs_reminder_worker_with_database_readiness_healthcheck() -> None:
    services_result = subprocess.run(
        _compose_cmd("config", "--services"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    config_result = subprocess.run(
        _compose_cmd("config"),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert services_result.returncode == 0, services_result.stderr
    assert "reminder-worker" in services_result.stdout.strip().split("\n")
    assert config_result.returncode == 0, config_result.stderr
    assert "tuck-reminder-worker" in config_result.stdout
    assert "--health-check" in config_result.stdout


def test_compose_injects_complete_vapid_settings_into_api_and_worker() -> None:
    result = subprocess.run(
        _compose_cmd("config"),
        env=os.environ
        | {
            "TUCK_VAPID_PUBLIC_KEY": "test-public-key",
            "TUCK_VAPID_PRIVATE_KEY": "test-private-key",
            "TUCK_VAPID_SUBJECT": "mailto:operator@example.invalid",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("TUCK_VAPID_PUBLIC_KEY: test-public-key") == 2
    assert result.stdout.count("TUCK_VAPID_PRIVATE_KEY: test-private-key") == 2
    assert result.stdout.count("TUCK_VAPID_SUBJECT: mailto:operator@example.invalid") == 2


def test_compose_postgres_has_healthcheck() -> None:
    """Validate that PostgreSQL service defines a healthcheck."""
    result = subprocess.run(
        _compose_cmd("config"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"compose config failed: {result.stderr}"
    # Verify postgres section contains healthcheck configuration
    # Note: config output may order services differently; find postgres block
    lines = result.stdout.split("\n")
    in_postgres = False
    postgres_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "postgres:" or stripped.startswith("postgres:"):
            in_postgres = True
            continue
        if in_postgres:
            # Top-level service boundary (2-space indent, not 4-space)
            if line.startswith("  ") and not line.startswith("    "):
                break
            postgres_lines.append(line)
    assert "healthcheck:" in "\n".join(postgres_lines), "postgres service missing healthcheck"
    assert "pg_isready" in result.stdout


def test_ci_postgres_credentials_match() -> None:
    workflow = Path(_REPO_ROOT, ".github", "workflows", "deploy.yml").read_text()

    assert "POSTGRES_PASSWORD: local-development-only" in workflow
    assert "postgresql://tuck:local-development-only@localhost:5432/postgres" in workflow
    assert "postgresql://tuck:***@localhost" not in workflow


def test_deploy_verifies_api_and_web_readiness() -> None:
    workflow = Path(_REPO_ROOT, ".github", "workflows", "deploy.yml").read_text()

    assert "--wait --wait-timeout 120" in workflow
    assert "curl --fail --silent --show-error http://localhost:8000/api/v1/ready" in workflow
    assert "wget --quiet --spider http://127.0.0.1:80/" in workflow


def test_deploy_defaults_to_runner_owned_production_config() -> None:
    workflow = Path(_REPO_ROOT, ".github", "workflows", "deploy.yml").read_text()

    assert "TUCK_ENV_FILE: ${{ vars.TUCK_ENV_FILE }}" in workflow
    assert 'TUCK_ENV_FILE="${TUCK_ENV_FILE:-$HOME/.config/tuck/tuck.env}"' in workflow
    assert 'echo "TUCK_ENV_FILE=$TUCK_ENV_FILE" >> "$GITHUB_ENV"' in workflow


def test_production_environment_bootstrap_creates_valid_private_file(tmp_path: Path) -> None:
    env_file = tmp_path / "config" / "tuck.env"
    bootstrap = Path(_REPO_ROOT, "scripts", "create-production-env.sh")

    result = subprocess.run(
        [bootstrap, env_file],
        cwd=_REPO_ROOT,
        capture_output=True,
        env={**os.environ, "TUCK_VAPID_SUBJECT": "mailto:operator@example.invalid"},
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert env_file.stat().st_mode & 0o777 == 0o600
    content = env_file.read_text()
    assert "local-development-only" not in content
    assert "TUCK_ENVIRONMENT=production" in content
    assert "@postgres:5432/tuck" in content
    assert "TUCK_VAPID_PUBLIC_KEY=" in content
    assert "TUCK_VAPID_PRIVATE_KEY='-----BEGIN EC PRIVATE KEY-----" in content
    assert "TUCK_VAPID_SUBJECT=mailto:operator@example.invalid" in content

    validation = subprocess.run(
        [_PRODUCTION_CONFIG_VALIDATOR, env_file],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert validation.returncode == 0, validation.stderr


def test_production_environment_bootstrap_requires_vapid_subject(tmp_path: Path) -> None:
    env_file = tmp_path / "tuck.env"
    bootstrap = Path(_REPO_ROOT, "scripts", "create-production-env.sh")

    result = subprocess.run(
        [bootstrap, env_file],
        cwd=_REPO_ROOT,
        capture_output=True,
        env={key: value for key, value in os.environ.items() if key != "TUCK_VAPID_SUBJECT"},
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert not env_file.exists()
    assert "TUCK_VAPID_SUBJECT must start with mailto: or https://" in result.stderr


def test_production_environment_bootstrap_refuses_to_overwrite(tmp_path: Path) -> None:
    env_file = tmp_path / "tuck.env"
    env_file.write_text("keep-me")
    bootstrap = Path(_REPO_ROOT, "scripts", "create-production-env.sh")

    result = subprocess.run(
        [bootstrap, env_file],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert env_file.read_text() == "keep-me"
    assert "already exists" in result.stderr


def test_runner_installer_pins_and_verifies_download() -> None:
    installer = Path(_REPO_ROOT, "scripts", "install-production-runner.sh")
    content = installer.read_text()

    assert os.access(installer, os.X_OK)
    assert "RUNNER_VERSION=" in content
    assert "RUNNER_SHA256=" in content
    assert "sha256sum --check" in content
    assert "TUCK_RUNNER_REGISTRATION_TOKEN" in content
    assert '--labels "tuck-production"' in content
    assert 'readonly runner_user="$(id -un)"' in content
    assert 'loginctl show-user "$runner_user" -p Linger --value' in content
    assert "ExecStart=$install_dir/bin/runsvc.sh" in content
    assert "systemctl --user enable --now tuck-actions-runner.service" in content

    unset_position = content.index("unset TUCK_RUNNER_REGISTRATION_TOKEN")
    download_position = content.index("curl --fail")
    assert unset_position < download_position


def test_production_environment_bootstrap_installs_atomically() -> None:
    bootstrap = Path(_REPO_ROOT, "scripts", "create-production-env.sh").read_text()

    assert 'ln -T -- "$temporary" "$target"' in bootstrap
    assert 'ln -- "$temporary" "$target"' not in bootstrap
    assert 'mv "$temporary" "$target"' not in bootstrap


def test_production_environment_bootstrap_refuses_dangling_symlink(tmp_path: Path) -> None:
    env_file = tmp_path / "tuck.env"
    env_file.symlink_to(tmp_path / "missing.env")
    bootstrap = Path(_REPO_ROOT, "scripts", "create-production-env.sh")

    result = subprocess.run(
        [bootstrap, env_file],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert env_file.is_symlink()
    assert not env_file.resolve().exists()
    assert "already exists" in result.stderr


def test_production_config_rejects_development_defaults(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text("TUCK_ENVIRONMENT=production\n")

    result = subprocess.run(
        [_PRODUCTION_CONFIG_VALIDATOR, str(env_file)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "development database password" in result.stderr


def test_production_config_rejects_missing_vapid_settings(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "\n".join(
            (
                "POSTGRES_PASSWORD=test-production-password",
                "TUCK_COMPOSE_DATABASE_URL=postgresql+asyncpg://tuck:"
                "test-production-password@postgres:5432/tuck",
                "TUCK_ENVIRONMENT=production",
            )
        )
    )

    result = subprocess.run(
        [_PRODUCTION_CONFIG_VALIDATOR, str(env_file)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "VAPID settings must all be non-empty" in result.stderr


def test_production_config_accepts_explicit_production_values(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "\n".join(
            (
                "POSTGRES_PASSWORD=test-production-password",
                "TUCK_COMPOSE_DATABASE_URL=postgresql+asyncpg://tuck:"
                "test-production-password@postgres:5432/tuck",
                "TUCK_ENVIRONMENT=production",
                "TUCK_VAPID_PUBLIC_KEY=test-public-key",
                "TUCK_VAPID_PRIVATE_KEY=test-private-key",
                "TUCK_VAPID_SUBJECT=mailto:operator@example.invalid",
            )
        )
    )

    result = subprocess.run(
        [_PRODUCTION_CONFIG_VALIDATOR, str(env_file)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
