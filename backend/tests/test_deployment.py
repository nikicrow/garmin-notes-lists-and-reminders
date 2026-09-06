"""Tests for deployment configuration."""

import os
import subprocess

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


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
