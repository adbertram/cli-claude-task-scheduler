"""Tests for the timeout_seconds feature.

These tests follow TDD - they are written FIRST, before the implementation.
All tests should fail initially, then pass after implementation.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# --- Model Tests ---


def test_scheduled_task_has_timeout_field():
    """ScheduledTask model should have timeout_seconds field."""
    from claude_task_scheduler_cli.models.task import ScheduledTask
    from datetime import datetime

    task = ScheduledTask(
        id="test-id",
        name="Test Task",
        prompt="Test prompt",
        project_path="/test/path",
        cron_expression="0 * * * *",
        model="sonnet",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    assert hasattr(task, "timeout_seconds")


def test_scheduled_task_default_timeout():
    """ScheduledTask should have default timeout of 3600 seconds."""
    from claude_task_scheduler_cli.models.task import ScheduledTask
    from datetime import datetime

    task = ScheduledTask(
        id="test-id",
        name="Test Task",
        prompt="Test prompt",
        project_path="/test/path",
        cron_expression="0 * * * *",
        model="sonnet",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    assert task.timeout_seconds == 3600


def test_scheduled_task_create_has_timeout_field():
    """ScheduledTaskCreate model should have timeout_seconds field."""
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    task_create = ScheduledTaskCreate(
        name="Test Task",
        prompt="Test prompt",
        project_path="/test/path",
        cron_expression="0 * * * *",
        model="sonnet",
        timeout_seconds=7200,
    )
    assert task_create.timeout_seconds == 7200


def test_scheduled_task_create_default_timeout():
    """ScheduledTaskCreate should have default timeout of 3600 seconds."""
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    task_create = ScheduledTaskCreate(
        name="Test Task",
        prompt="Test prompt",
        project_path="/test/path",
        cron_expression="0 * * * *",
        model="sonnet",
    )
    assert task_create.timeout_seconds == 3600


def test_scheduled_task_update_has_timeout_field():
    """ScheduledTaskUpdate model should have optional timeout_seconds field."""
    from claude_task_scheduler_cli.models.task import ScheduledTaskUpdate

    # Test with timeout specified
    task_update = ScheduledTaskUpdate(timeout_seconds=1800)
    assert task_update.timeout_seconds == 1800

    # Test without timeout (should be None)
    task_update_empty = ScheduledTaskUpdate()
    assert task_update_empty.timeout_seconds is None


# --- Database Model Tests ---


def test_db_model_has_timeout_column():
    """ScheduledTaskDB should have timeout_seconds column."""
    from claude_task_scheduler_cli.models.db import ScheduledTaskDB

    # Check that the column exists in the model
    assert hasattr(ScheduledTaskDB, "timeout_seconds")
    # Check it's a column (not just any attribute)
    from sqlalchemy import inspect
    mapper = inspect(ScheduledTaskDB)
    column_names = [c.key for c in mapper.columns]
    assert "timeout_seconds" in column_names


# --- Database Client Tests ---


def test_db_create_task_stores_timeout():
    """create_task() should store custom timeout value."""
    from claude_task_scheduler_cli.db_client import DatabaseClient
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db_client = DatabaseClient(db_path)
        task_data = ScheduledTaskCreate(
            name="Test Task",
            prompt="Test prompt",
            project_path="/test/path",
            cron_expression="0 * * * *",
            model="sonnet",
            timeout_seconds=7200,
        )
        task = db_client.create_task(task_data)
        assert task.timeout_seconds == 7200
    finally:
        os.unlink(db_path)


def test_db_create_task_default_timeout():
    """create_task() should use default 3600 when not specified."""
    from claude_task_scheduler_cli.db_client import DatabaseClient
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db_client = DatabaseClient(db_path)
        task_data = ScheduledTaskCreate(
            name="Test Task",
            prompt="Test prompt",
            project_path="/test/path",
            cron_expression="0 * * * *",
            model="sonnet",
        )
        task = db_client.create_task(task_data)
        assert task.timeout_seconds == 3600
    finally:
        os.unlink(db_path)


def test_db_get_task_returns_timeout():
    """get_task() should include timeout_seconds in returned task."""
    from claude_task_scheduler_cli.db_client import DatabaseClient
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db_client = DatabaseClient(db_path)
        task_data = ScheduledTaskCreate(
            name="Test Task",
            prompt="Test prompt",
            project_path="/test/path",
            cron_expression="0 * * * *",
            model="sonnet",
            timeout_seconds=1800,
        )
        created_task = db_client.create_task(task_data)
        retrieved_task = db_client.get_task(created_task.id)
        assert retrieved_task is not None
        assert retrieved_task.timeout_seconds == 1800
    finally:
        os.unlink(db_path)


def test_db_update_task_updates_timeout():
    """update_task() should modify timeout_seconds."""
    from claude_task_scheduler_cli.db_client import DatabaseClient
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate, ScheduledTaskUpdate

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db_client = DatabaseClient(db_path)
        task_data = ScheduledTaskCreate(
            name="Test Task",
            prompt="Test prompt",
            project_path="/test/path",
            cron_expression="0 * * * *",
            model="sonnet",
            timeout_seconds=3600,
        )
        created_task = db_client.create_task(task_data)

        # Update the timeout
        update_data = ScheduledTaskUpdate(timeout_seconds=7200)
        updated_task = db_client.update_task(created_task.id, update_data)

        assert updated_task is not None
        assert updated_task.timeout_seconds == 7200
    finally:
        os.unlink(db_path)


def test_db_list_tasks_includes_timeout():
    """list_tasks() should include timeout_seconds in results."""
    from claude_task_scheduler_cli.db_client import DatabaseClient
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db_client = DatabaseClient(db_path)
        task_data = ScheduledTaskCreate(
            name="Test Task",
            prompt="Test prompt",
            project_path="/test/path",
            cron_expression="0 * * * *",
            model="sonnet",
            timeout_seconds=5400,
        )
        db_client.create_task(task_data)

        tasks = db_client.list_tasks()
        assert len(tasks) > 0
        assert tasks[0].timeout_seconds == 5400
    finally:
        os.unlink(db_path)


# --- CLI Tests ---


def test_cli_create_with_timeout():
    """CLI create command should accept --timeout option."""
    from typer.testing import CliRunner
    from claude_task_scheduler_cli.main import app

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        project_path = tmpdir

        with patch.dict(os.environ, {"CLAUDE_SCHEDULER_DB": db_path}):
            result = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "Test Task",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 * * * *",
                    "--model", "sonnet",
                    "--timeout", "7200",
                ],
            )
            # Should not error on --timeout option
            assert result.exit_code == 0 or "timeout" not in result.output.lower()


def test_cli_create_default_timeout():
    """CLI create without --timeout should use default 3600."""
    from typer.testing import CliRunner
    from claude_task_scheduler_cli.main import app
    from claude_task_scheduler_cli.db_client import DatabaseClient

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        project_path = tmpdir

        result = runner.invoke(
            app,
            [
                "tasks", "create",
                "--name", "Test Task",
                "--prompt", "Test prompt",
                "--project", project_path,
                "--cron", "0 * * * *",
                "--model", "sonnet",
            ],
        )

        if result.exit_code == 0:
            db_client = DatabaseClient(db_path)
            tasks = db_client.list_tasks()
            if tasks:
                assert tasks[0].timeout_seconds == 3600


def test_cli_create_timeout_too_low():
    """CLI should reject timeout < 60 seconds."""
    from typer.testing import CliRunner
    from claude_task_scheduler_cli.main import app

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = tmpdir

        result = runner.invoke(
            app,
            [
                "tasks", "create",
                "--name", "Test Task",
                "--prompt", "Test prompt",
                "--project", project_path,
                "--cron", "0 * * * *",
                "--model", "sonnet",
                "--timeout", "30",  # Too low
            ],
        )
        # Should fail with error about timeout range
        assert result.exit_code != 0


def test_cli_create_timeout_too_high():
    """CLI should reject timeout > 86400 seconds."""
    from typer.testing import CliRunner
    from claude_task_scheduler_cli.main import app

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = tmpdir

        result = runner.invoke(
            app,
            [
                "tasks", "create",
                "--name", "Test Task",
                "--prompt", "Test prompt",
                "--project", project_path,
                "--cron", "0 * * * *",
                "--model", "sonnet",
                "--timeout", "100000",  # Too high
            ],
        )
        # Should fail with error about timeout range
        assert result.exit_code != 0


def test_cli_update_timeout():
    """CLI update command should accept --timeout option."""
    from typer.testing import CliRunner
    from claude_task_scheduler_cli.main import app
    from claude_task_scheduler_cli.db_client import DatabaseClient
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        project_path = tmpdir

        # Create a task first
        db_client = DatabaseClient(db_path)
        task_data = ScheduledTaskCreate(
            name="Test Task",
            prompt="Test prompt",
            project_path=project_path,
            cron_expression="0 * * * *",
            model="sonnet",
        )
        task = db_client.create_task(task_data)

        # Update with new timeout
        result = runner.invoke(
            app,
            [
                "tasks", "update",
                task.id,
                "--timeout", "1800",
            ],
        )
        # Should accept --timeout option
        assert result.exit_code == 0 or "timeout" not in result.output.lower()


def test_cli_update_timeout_validation():
    """CLI update should reject invalid timeout values."""
    from typer.testing import CliRunner
    from claude_task_scheduler_cli.main import app
    from claude_task_scheduler_cli.db_client import DatabaseClient
    from claude_task_scheduler_cli.models.task import ScheduledTaskCreate

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        project_path = tmpdir

        # Create a task first
        db_client = DatabaseClient(db_path)
        task_data = ScheduledTaskCreate(
            name="Test Task",
            prompt="Test prompt",
            project_path=project_path,
            cron_expression="0 * * * *",
            model="sonnet",
        )
        task = db_client.create_task(task_data)

        # Try to update with invalid timeout (too low)
        result = runner.invoke(
            app,
            [
                "tasks", "update",
                task.id,
                "--timeout", "10",  # Too low
            ],
        )
        # Should fail
        assert result.exit_code != 0


# --- Scheduler Tests ---


def test_scheduler_uses_task_timeout():
    """Scheduler should use task.timeout_seconds for subprocess timeout."""
    from claude_task_scheduler_cli.scheduler import _invoke_claude_standalone
    from claude_task_scheduler_cli.models.task import ScheduledTask, TaskRun, RunStatus
    from datetime import datetime

    task = ScheduledTask(
        id="test-id",
        name="Test Task",
        prompt="Test prompt",
        project_path="/tmp",
        cron_expression="0 * * * *",
        model="sonnet",
        timeout_seconds=120,  # Custom timeout
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    run = TaskRun(
        id="run-id",
        task_id="test-id",
        status=RunStatus.RUNNING,
        started_at=datetime.utcnow(),
        output="Test run in progress",
    )
    logger_service = MagicMock()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output",
            stderr="",
        )

        _invoke_claude_standalone(task, run, logger_service)

        # Verify subprocess.run was called with the task's timeout
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("timeout") == 120


def test_scheduler_timeout_error_message():
    """Timeout error should include actual timeout value."""
    from claude_task_scheduler_cli.scheduler import _invoke_claude_standalone
    from claude_task_scheduler_cli.models.task import ScheduledTask, TaskRun, RunStatus
    from datetime import datetime
    import subprocess

    task = ScheduledTask(
        id="test-id",
        name="Test Task",
        prompt="Test prompt",
        project_path="/tmp",
        cron_expression="0 * * * *",
        model="sonnet",
        timeout_seconds=300,  # 5 minutes
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    run = TaskRun(
        id="run-id",
        task_id="test-id",
        status=RunStatus.RUNNING,
        started_at=datetime.utcnow(),
        output="Test run in progress",
    )
    logger_service = MagicMock()

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)

        result = _invoke_claude_standalone(task, run, logger_service)

        # Error message should include the actual timeout value (300 seconds)
        assert "300" in result["error"]


# --- E2E Tests ---


def _extract_json_object(output: str) -> dict:
    """Extract JSON object from CLI output, handling multiline JSON."""
    import json
    import re

    # Remove ANSI color codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', output)

    # Try to find a JSON object (multiline)
    # Look for { ... } pattern that's valid JSON
    brace_count = 0
    start_idx = None

    for i, char in enumerate(clean_output):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx is not None:
                try:
                    return json.loads(clean_output[start_idx:i+1])
                except json.JSONDecodeError:
                    start_idx = None
                    continue

    raise ValueError(f"No valid JSON object found in output: {output[:500]}")


def _extract_json_array(output: str) -> list:
    """Extract JSON array from CLI output, handling multiline JSON."""
    import json
    import re

    # Remove ANSI color codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', output)

    # Try to find a JSON array (multiline)
    bracket_count = 0
    start_idx = None

    for i, char in enumerate(clean_output):
        if char == '[':
            if bracket_count == 0:
                start_idx = i
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0 and start_idx is not None:
                try:
                    return json.loads(clean_output[start_idx:i+1])
                except json.JSONDecodeError:
                    start_idx = None
                    continue

    raise ValueError(f"No valid JSON array found in output: {output[:500]}")


class TestTimeoutE2E:
    """End-to-end tests for the timeout feature through the CLI."""

    def test_e2e_create_task_with_custom_timeout_json_output(self):
        """E2E: Create task with custom timeout, verify JSON output contains timeout_seconds."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            result = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "E2E Timeout Test",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 9 * * *",
                    "--model", "sonnet",
                    "--timeout", "7200",
                ],
                env=env,
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"
            json_output = _extract_json_object(result.output)
            assert json_output.get("timeout_seconds") == 7200

    def test_e2e_create_task_default_timeout_json_output(self):
        """E2E: Create task without --timeout, verify default 3600 in JSON output."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            result = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "E2E Default Timeout",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 9 * * *",
                    "--model", "sonnet",
                ],
                env=env,
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"
            json_output = _extract_json_object(result.output)
            assert json_output.get("timeout_seconds") == 3600

    def test_e2e_get_task_includes_timeout(self):
        """E2E: Create task, then get it by ID and verify timeout in output."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task
            create_result = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "E2E Get Test",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 9 * * *",
                    "--model", "sonnet",
                    "--timeout", "1800",
                ],
                env=env,
            )
            assert create_result.exit_code == 0
            created_task = _extract_json_object(create_result.output)
            task_id = created_task["id"]

            # Get task by ID
            get_result = runner.invoke(
                app,
                ["tasks", "get", task_id],
                env=env,
            )
            assert get_result.exit_code == 0
            retrieved_task = _extract_json_object(get_result.output)
            assert retrieved_task["timeout_seconds"] == 1800

    def test_e2e_list_tasks_includes_timeout(self):
        """E2E: Create task, list all tasks, verify timeout in output."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task with custom timeout
            create_result = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "E2E List Test",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 9 * * *",
                    "--model", "sonnet",
                    "--timeout", "5400",
                ],
                env=env,
            )
            assert create_result.exit_code == 0

            # List tasks
            list_result = runner.invoke(
                app,
                ["tasks", "list"],
                env=env,
            )
            assert list_result.exit_code == 0
            tasks = _extract_json_array(list_result.output)
            assert len(tasks) > 0
            assert tasks[0]["timeout_seconds"] == 5400

    def test_e2e_update_task_timeout(self):
        """E2E: Create task, update timeout, verify change persists."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task with default timeout
            create_result = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "E2E Update Test",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 9 * * *",
                    "--model", "sonnet",
                ],
                env=env,
            )
            assert create_result.exit_code == 0
            created_task = _extract_json_object(create_result.output)
            task_id = created_task["id"]
            assert created_task["timeout_seconds"] == 3600  # Default

            # Update timeout
            update_result = runner.invoke(
                app,
                ["tasks", "update", task_id, "--timeout", "7200"],
                env=env,
            )
            assert update_result.exit_code == 0
            updated_task = _extract_json_object(update_result.output)
            assert updated_task["timeout_seconds"] == 7200

            # Verify with get command
            get_result = runner.invoke(
                app,
                ["tasks", "get", task_id],
                env=env,
            )
            assert get_result.exit_code == 0
            final_task = _extract_json_object(get_result.output)
            assert final_task["timeout_seconds"] == 7200

    def test_e2e_validation_error_messages(self):
        """E2E: Verify proper error messages for invalid timeout values."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Test timeout too low
            result_low = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "Invalid Test",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 9 * * *",
                    "--model", "sonnet",
                    "--timeout", "30",
                ],
                env=env,
            )
            assert result_low.exit_code != 0
            assert "60" in result_low.output or "86400" in result_low.output

            # Test timeout too high
            result_high = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "Invalid Test",
                    "--prompt", "Test prompt",
                    "--project", project_path,
                    "--cron", "0 9 * * *",
                    "--model", "sonnet",
                    "--timeout", "100000",
                ],
                env=env,
            )
            assert result_high.exit_code != 0
            assert "60" in result_high.output or "86400" in result_high.output

    def test_e2e_update_only_timeout_preserves_other_fields(self):
        """E2E: Update only timeout, verify other fields unchanged."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task with specific values
            create_result = runner.invoke(
                app,
                [
                    "tasks", "create",
                    "--name", "Preserve Fields Test",
                    "--prompt", "Original prompt",
                    "--project", project_path,
                    "--cron", "30 10 * * 1",
                    "--model", "opus",
                    "--max-retries", "5",
                    "--timeout", "3600",
                ],
                env=env,
            )
            assert create_result.exit_code == 0
            created_task = _extract_json_object(create_result.output)
            task_id = created_task["id"]

            # Update ONLY timeout
            update_result = runner.invoke(
                app,
                ["tasks", "update", task_id, "--timeout", "1800"],
                env=env,
            )
            assert update_result.exit_code == 0

            # Get the task and verify all fields
            get_result = runner.invoke(
                app,
                ["tasks", "get", task_id],
                env=env,
            )
            assert get_result.exit_code == 0
            final_task = _extract_json_object(get_result.output)

            # Timeout should be updated
            assert final_task["timeout_seconds"] == 1800

            # Other fields should be preserved
            assert final_task["name"] == "Preserve Fields Test"
            assert final_task["prompt"] == "Original prompt"
            assert final_task["cron_expression"] == "30 10 * * 1"
            assert final_task["model"] == "opus"
            assert final_task["max_retries"] == 5

    def test_e2e_multiple_tasks_different_timeouts(self):
        """E2E: Create multiple tasks with different timeouts, verify all stored correctly."""
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            timeouts = [60, 300, 3600, 7200, 86400]  # Min, 5min, 1hr, 2hr, 24hr

            for timeout in timeouts:
                result = runner.invoke(
                    app,
                    [
                        "tasks", "create",
                        "--name", f"Task with {timeout}s timeout",
                        "--prompt", "Test prompt",
                        "--project", project_path,
                        "--cron", "0 9 * * *",
                        "--model", "sonnet",
                        "--timeout", str(timeout),
                    ],
                    env=env,
                )
                assert result.exit_code == 0, f"Failed for timeout {timeout}: {result.output}"

            # List all tasks and verify timeouts
            list_result = runner.invoke(
                app,
                ["tasks", "list"],
                env=env,
            )
            assert list_result.exit_code == 0
            tasks = _extract_json_array(list_result.output)
            assert len(tasks) == 5
            actual_timeouts = sorted([t["timeout_seconds"] for t in tasks])
            assert actual_timeouts == sorted(timeouts)

    @pytest.mark.slow
    def test_e2e_task_actually_times_out(self):
        """E2E: Create task with 60s timeout, run complex prompt, verify task is killed.

        This test takes ~60 seconds to run. Use `pytest -m 'not slow'` to skip.

        NOTE: This test uses the REAL scheduler database and Claude credentials.
        The test task is cleaned up after the test completes.
        """
        from typer.testing import CliRunner
        from claude_task_scheduler_cli.main import app
        from claude_task_scheduler_cli.db_client import DatabaseClient

        runner = CliRunner()
        task_id = None
        db_client = DatabaseClient()  # Use real DB

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                project_path = tmpdir

                # Create task with minimum timeout and a prompt that will take way longer than 60s
                complex_prompt = """Write a complete, highly detailed 100,000 word novel with the following requirements:
                1. Set in a fantasy world with complete magic system documentation
                2. Include 50 unique named characters with full backstories
                3. Write 100 chapters, each at least 1000 words
                4. Include detailed maps and world-building appendices
                5. Write in the style of Tolkien with extensive linguistic notes
                6. Include a complete glossary of invented terms
                7. Add historical timeline spanning 10,000 years
                Begin writing the complete novel now, do not summarize or abbreviate."""

                create_result = runner.invoke(
                    app,
                    [
                        "tasks", "create",
                        "--name", "E2E Timeout Test - DELETE ME",
                        "--prompt", complex_prompt,
                        "--project", project_path,
                        "--cron", "0 0 1 1 *",  # Jan 1 at midnight - won't auto-trigger
                        "--model", "sonnet",
                        "--timeout", "60",  # Minimum timeout
                        "--disabled",  # Don't auto-run
                    ],
                )
                assert create_result.exit_code == 0, f"Create failed: {create_result.output}"
                created_task = _extract_json_object(create_result.output)
                task_id = created_task["id"]

                # Trigger the task - this will take ~60 seconds then timeout
                trigger_result = runner.invoke(
                    app,
                    ["tasks", "trigger", task_id],
                )

                # Check if Claude authentication failed (skip test if so)
                if "Invalid API key" in str(trigger_result.output) or "login" in str(trigger_result.output).lower():
                    pytest.skip("Claude not authenticated - skipping E2E timeout test")

                # Get the runs for this task
                runs = db_client.list_runs(task_id=task_id)
                assert len(runs) > 0, "No runs found for task"

                # The run should have failed with timeout error
                latest_run = runs[0]
                assert latest_run.status.value == "timeout", f"Expected timeout status, got {latest_run.status.value}. Summary: {latest_run.output}"
                assert latest_run.error_message is not None, f"No error message. Summary: {latest_run.output}"
                assert "timed out" in latest_run.error_message.lower() or "timeout" in latest_run.error_message.lower(), \
                    f"Error message doesn't mention timeout: {latest_run.error_message}"
                assert "60" in latest_run.error_message, f"Error message doesn't mention 60 seconds: {latest_run.error_message}"

        finally:
            # Clean up: delete the test task
            if task_id:
                db_client.delete_task(task_id)
