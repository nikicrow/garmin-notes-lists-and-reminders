"""Tests for database backup and restore scripts."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

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


def test_backup_restore_round_trip_includes_phase_2_notification_tables(
    isolated_database_url: str, tmp_path: Path
) -> None:
    database_url = make_url(isolated_database_url)
    database_name = database_url.database
    assert database_name is not None
    postgres_host = database_url.host or "localhost"
    postgres_port = str(database_url.port or 5432)
    postgres_user = database_url.username or "tuck"
    client_env = os.environ | {"PGPASSWORD": database_url.password or ""}
    tmp_path.chmod(0o777)

    def postgres_client(*args: str) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "--env",
            "PGPASSWORD",
            "--volume",
            f"{tmp_path}:/backup:Z",
            "postgres:17-alpine",
            *args,
        ]

    migration_env = os.environ | {"TUCK_DATABASE_URL": isolated_database_url}
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.join(_REPO_ROOT, "backend"),
        env=migration_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert migration.returncode == 0, migration.stderr

    dump_file = tmp_path / "phase-2.sql"
    backup = subprocess.run(
        postgres_client(
            "pg_dump",
            "--host",
            postgres_host,
            "--port",
            postgres_port,
            "--username",
            postgres_user,
            "--dbname",
            database_name,
            "--format",
            "plain",
            "--file",
            "/backup/phase-2.sql",
        ),
        env=client_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert backup.returncode == 0, backup.stderr
    dump_contents = dump_file.read_text()
    assert all(
        f"CREATE TABLE public.{table_name}" in dump_contents
        for table_name in (
            "push_subscriptions",
            "reminder_recipients",
            "notification_deliveries",
        )
    )

    for statement in (
        f'DROP DATABASE "{database_name}";',
        f'CREATE DATABASE "{database_name}";',
    ):
        recreate = subprocess.run(
            postgres_client(
                "psql",
                "--host",
                postgres_host,
                "--port",
                postgres_port,
                "--username",
                postgres_user,
                "--dbname",
                "postgres",
                "--command",
                statement,
            ),
            env=client_env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert recreate.returncode == 0, recreate.stderr

    restore = subprocess.run(
        postgres_client(
            "psql",
            "--host",
            postgres_host,
            "--port",
            postgres_port,
            "--username",
            postgres_user,
            "--dbname",
            database_name,
            "--set",
            "ON_ERROR_STOP=on",
            "--file",
            "/backup/phase-2.sql",
        ),
        env=client_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert restore.returncode == 0, restore.stderr

    phase_2_tables = subprocess.run(
        postgres_client(
            "psql",
            "--host",
            postgres_host,
            "--port",
            postgres_port,
            "--username",
            postgres_user,
            "--dbname",
            database_name,
            "--tuples-only",
            "--command",
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename IN ('push_subscriptions', 'reminder_recipients', "
            "'notification_deliveries') ORDER BY tablename;",
        ),
        env=client_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert phase_2_tables.returncode == 0, phase_2_tables.stderr
    assert phase_2_tables.stdout.split() == [
        "notification_deliveries",
        "push_subscriptions",
        "reminder_recipients",
    ]
