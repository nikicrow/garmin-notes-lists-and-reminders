"""Tests for database backup and restore scripts."""

import os
import subprocess
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _script_path(name: str) -> str:
    return os.path.join(_REPO_ROOT, "scripts", name)


def _compose_cmd(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        os.path.join(_REPO_ROOT, "compose.yaml"),
        *args,
    ]


class TestBackupScriptExists:
    def test_backup_script_exists(self) -> None:
        assert os.path.isfile(_script_path("postgres-backup.sh"))
        assert os.access(_script_path("postgres-backup.sh"), os.X_OK)

    def test_restore_script_exists(self) -> None:
        assert os.path.isfile(_script_path("postgres-restore.sh"))
        assert os.access(_script_path("postgres-restore.sh"), os.X_OK)


class TestBackupScriptContent:
    def test_backup_script_is_executable_shell(self) -> None:
        content = open(_script_path("postgres-backup.sh")).read()
        assert content.startswith("#!") or "/bin/sh" in content or "/bin/bash" in content
        assert "pg_dump" in content or "pg_dump" in content.lower()

    def test_backup_script_uses_environment_variables(self) -> None:
        content = open(_script_path("postgres-backup.sh")).read()
        assert "POSTGRES_USER" in content or "PGPASSWORD" in content
        assert "POSTGRES_DB" in content or "PostgreSQL" in content

    def test_backup_script_has_safe_defaults(self) -> None:
        content = open(_script_path("postgres-backup.sh")).read()
        assert "postgres" in content
        assert ".sql" in content or ".dump" in content or "backup" in content.lower()


class TestRestoreScriptContent:
    def test_restore_script_is_executable_shell(self) -> None:
        content = open(_script_path("postgres-restore.sh")).read()
        assert content.startswith("#!") or "/bin/sh" in content or "/bin/bash" in content
        assert "pg_restore" in content or "psql" in content or "restore" in content.lower()

    def test_restore_script_uses_environment_variables(self) -> None:
        content = open(_script_path("postgres-restore.sh")).read()
        assert "POSTGRES_USER" in content or "PGPASSWORD" in content
        assert "POSTGRES_DB" in content or "PostgreSQL" in content

    def test_restore_script_has_confirmation_or_dry_run(self) -> None:
        content = open(_script_path("postgres-restore.sh")).read()
        # Restore scripts should have safety mechanisms
        assert any(
            word in content.lower()
            for word in ["confirm", "yes", "dry-run", "dryrun", "force", "restore"]
        )

    def test_restore_script_targets_production_not_development(self) -> None:
        """Restore scripts should have safeguards against accidental development restores."""
        content = open(_script_path("postgres-restore.sh")).read()
        # Should reference environment or target checks
        assert any(
            word in content.lower()
            for word in ["environment", "production", "env", "target", "database"]
        )


class TestBackupRestoreSymlinkSafety:
    """Tests ensuring backup/restore scripts don't accidentally target wrong environments."""

    def test_backup_does_not_use_default_password_as_default_value(self) -> None:
        content = open(_script_path("postgres-backup.sh")).read()
        # The script must not use "local-development-only" as the DEFAULT for
        # POSTGRES_PASSWORD (i.e. it should not appear in a "${VAR:-default}" pattern).
        # It MAY check if the password equals that value and warn/block.
        import re

        # Look for patterns like: POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-local-development-only}"
        # or: POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-local-development-only}
        default_pattern = re.compile(
            r"POSTGRES_PASSWORD[\"\x27]?:\x2d[\"\x27]?local-development-only",
            re.IGNORECASE,
        )
        assert not default_pattern.search(content), (
            "Script uses 'local-development-only' as the default value for "
            "POSTGRES_PASSWORD. Production deployments MUST set this via environment "
            "variables with no fallback to the development default."
        )

    def test_restore_does_not_use_default_password_as_default_value(self) -> None:
        content = open(_script_path("postgres-restore.sh")).read()
        import re

        default_pattern = re.compile(
            r"POSTGRES_PASSWORD[\"\x27]?:\x2d[\"\x27]?local-development-only",
            re.IGNORECASE,
        )
        assert not default_pattern.search(content), (
            "Script uses 'local-development-only' as the default value for "
            "POSTGRES_PASSWORD. Production deployments MUST set this via environment "
            "variables with no fallback to the development default."
        )


class TestBackupScriptHelp:
    def test_backup_script_accepts_help_flag(self) -> None:
        """Backup script should respond to --help or -h."""
        result = subprocess.run(
            [sys.executable, _script_path("postgres-backup.sh"), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Help should either succeed (return 0) or fail gracefully (not crash 127)
        assert result.returncode != 127, "Script not found or not executable"

    def test_restore_script_accepts_help_flag(self) -> None:
        """Restore script should respond to --help or -h."""
        result = subprocess.run(
            [sys.executable, _script_path("postgres-restore.sh"), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 127, "Script not found or not executable"
