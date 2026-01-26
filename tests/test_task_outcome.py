"""E2E and unit tests for TaskOutcome semantic status feature.

All E2E tests use CLI only via subprocess - no internal Python function calls.
"""

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest


# === CLI Helpers (same pattern as test_task_run_creation.py) ===

def _run_cli(args: list[str], env: dict = None) -> subprocess.CompletedProcess:
    """Run the CLI and return the result."""
    cmd = ["claude-task-scheduler"] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def _extract_json_object(output: str) -> dict:
    """Extract JSON object from CLI output."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', output).strip()

    # First try: parse the entire output as JSON directly
    try:
        return json.loads(clean_output)
    except json.JSONDecodeError:
        pass

    # Second try: find first { and parse from there to the end
    # This handles cases where there's leading text before JSON
    first_brace = clean_output.find('{')
    if first_brace != -1:
        try:
            return json.loads(clean_output[first_brace:])
        except json.JSONDecodeError:
            pass

    # Third try: find matching braces (fallback, may fail with nested braces in strings)
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
    """Extract JSON array from CLI output."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', output)

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


# === Unit Tests: Enum ===

class TestTaskOutcomeEnum:
    """Unit tests for TaskOutcome enum."""

    def test_task_outcome_enum_has_required_values(self):
        """TaskOutcome enum must have SUCCESS, FAILED, UNKNOWN values."""
        from claude_task_scheduler_cli.models.task import TaskOutcome

        assert TaskOutcome.SUCCESS.value == "success"
        assert TaskOutcome.FAILED.value == "failed"
        assert TaskOutcome.UNKNOWN.value == "unknown"

    def test_task_outcome_is_string_enum(self):
        """TaskOutcome values should be usable as strings."""
        from claude_task_scheduler_cli.models.task import TaskOutcome

        assert TaskOutcome.SUCCESS.value == "success"
        assert TaskOutcome("success") == TaskOutcome.SUCCESS


# === Unit Tests: Parser ===

class TestParseTaskOutcome:
    """Unit tests for parse_task_outcome function."""

    def test_parse_success(self):
        """Parse TASK_STATUS: SUCCESS marker."""
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        output = "Task completed.\n\nTASK_STATUS: SUCCESS"
        outcome, reason = parse_task_outcome(output)

        assert outcome == TaskOutcome.SUCCESS
        assert reason is None

    def test_parse_failed_with_reason(self):
        """Parse TASK_STATUS: FAILED with reason."""
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        output = "Could not complete.\n\nTASK_STATUS: FAILED - API rate limit exceeded"
        outcome, reason = parse_task_outcome(output)

        assert outcome == TaskOutcome.FAILED
        assert reason == "API rate limit exceeded"

    def test_parse_failed_without_reason(self):
        """Parse TASK_STATUS: FAILED without reason."""
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        output = "Failed.\n\nTASK_STATUS: FAILED"
        outcome, reason = parse_task_outcome(output)

        assert outcome == TaskOutcome.FAILED
        assert reason is None

    def test_parse_unknown_when_no_marker(self):
        """Return UNKNOWN when no marker found."""
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        output = "Task completed without status marker."
        outcome, reason = parse_task_outcome(output)

        assert outcome == TaskOutcome.UNKNOWN
        assert reason is None

    def test_parse_unknown_when_empty(self):
        """Return UNKNOWN for empty output."""
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        outcome, reason = parse_task_outcome("")
        assert outcome == TaskOutcome.UNKNOWN

        outcome, reason = parse_task_outcome(None)
        assert outcome == TaskOutcome.UNKNOWN

    def test_parse_case_insensitive(self):
        """Marker parsing should be case-insensitive."""
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        assert parse_task_outcome("task_status: success")[0] == TaskOutcome.SUCCESS
        assert parse_task_outcome("TASK_STATUS: FAILED")[0] == TaskOutcome.FAILED
        assert parse_task_outcome("Task_Status: Success")[0] == TaskOutcome.SUCCESS

    def test_parse_from_json_output(self):
        """Parse marker from Claude's --output-format json structure."""
        import json as json_module
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        json_output = json_module.dumps([
            {"type": "system", "subtype": "init"},
            {"type": "result", "result": "Done.\n\nTASK_STATUS: SUCCESS"}
        ])

        outcome, reason = parse_task_outcome(json_output)
        assert outcome == TaskOutcome.SUCCESS

    def test_parse_marker_in_middle_of_text(self):
        """Marker can appear anywhere in output."""
        from claude_task_scheduler_cli.scheduler import parse_task_outcome
        from claude_task_scheduler_cli.models.task import TaskOutcome

        output = "Line 1\nTASK_STATUS: FAILED - something broke\nLine 3"
        outcome, reason = parse_task_outcome(output)

        assert outcome == TaskOutcome.FAILED
        assert reason == "something broke"


# === Unit Tests: Model ===

class TestTaskRunModelOutcomeFields:
    """Unit tests for TaskRun model outcome fields."""

    def test_task_run_has_outcome_fields(self):
        """TaskRun model must have task_outcome and task_outcome_reason."""
        from claude_task_scheduler_cli.models.task import TaskRun, TaskOutcome, RunStatus

        run = TaskRun(
            id="test-run",
            task_id="test-task",
            status=RunStatus.SUCCESS,
            started_at=datetime.utcnow(),
            output="test",
            task_outcome=TaskOutcome.SUCCESS,
            task_outcome_reason=None,
        )

        assert run.task_outcome == TaskOutcome.SUCCESS
        assert run.task_outcome_reason is None

    def test_task_run_default_outcome_is_unknown(self):
        """TaskRun should default task_outcome to UNKNOWN."""
        from claude_task_scheduler_cli.models.task import TaskRun, TaskOutcome, RunStatus

        run = TaskRun(
            id="test-run",
            task_id="test-task",
            status=RunStatus.RUNNING,
            started_at=datetime.utcnow(),
            output="",
        )

        assert run.task_outcome == TaskOutcome.UNKNOWN
        assert run.task_outcome_reason is None

    def test_task_run_with_failed_outcome_and_reason(self):
        """TaskRun can store FAILED outcome with reason."""
        from claude_task_scheduler_cli.models.task import TaskRun, TaskOutcome, RunStatus

        run = TaskRun(
            id="test-run",
            task_id="test-task",
            status=RunStatus.SUCCESS,  # Process succeeded
            started_at=datetime.utcnow(),
            output="test",
            task_outcome=TaskOutcome.FAILED,  # But task failed
            task_outcome_reason="Could not find file",
        )

        assert run.task_outcome == TaskOutcome.FAILED
        assert run.task_outcome_reason == "Could not find file"


# === Unit Tests: Database Schema ===

class TestTaskRunDBOutcomeColumns:
    """Unit tests for TaskRunDB schema."""

    def test_db_has_outcome_columns(self, tmp_path):
        """TaskRunDB must have task_outcome and task_outcome_reason columns."""
        from sqlalchemy import create_engine, inspect
        from claude_task_scheduler_cli.models.db import Base

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("task_runs")}

        assert "task_outcome" in columns
        assert "task_outcome_reason" in columns


# === Unit Tests: Base Prompt ===

class TestBasePromptIncludesTaskStatusInstruction:
    """Unit tests for base prompt content."""

    def test_prompt_has_status_instruction(self):
        """BASE_PROMPT must instruct Claude to output status marker."""
        from claude_task_scheduler_cli.scheduler import BASE_PROMPT

        assert "TASK_STATUS:" in BASE_PROMPT
        assert "SUCCESS" in BASE_PROMPT
        assert "FAILED" in BASE_PROMPT


# === E2E Tests: CLI Output Shows Outcome ===

class TestTaskOutcomeCLI:
    """E2E tests verifying task_outcome is stored and displayed via CLI."""

    def test_runs_list_shows_task_outcome_column(self):
        """E2E: `runs list` output includes task_outcome field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create a task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "E2E Outcome Test",
                "--prompt", "Test prompt",
                "--project", tmpdir,
                "--cron", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0, f"Create failed: {create_result.stderr}"
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            # Trigger the task
            trigger_result = _run_cli(["tasks", "trigger", task_id], env=env)
            assert trigger_result.returncode == 0, f"Trigger failed: {trigger_result.stderr}"

            # List runs and verify task_outcome field exists
            runs_result = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            assert runs_result.returncode == 0, f"List runs failed: {runs_result.stderr}"

            runs = _extract_json_array(runs_result.stdout)
            assert len(runs) >= 1, "Expected at least one run"

            run = runs[0]
            assert "task_outcome" in run, f"Run missing task_outcome field: {run.keys()}"
            assert run["task_outcome"] in ["success", "failed", "unknown"], \
                f"Invalid task_outcome value: {run['task_outcome']}"

    def test_runs_get_shows_task_outcome_and_reason(self):
        """E2E: `runs get <id>` output includes task_outcome and task_outcome_reason."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create and trigger a task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "E2E Outcome Detail Test",
                "--prompt", "Test prompt",
                "--project", tmpdir,
                "--cron", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            # Trigger
            trigger_result = _run_cli(["tasks", "trigger", task_id], env=env)
            assert trigger_result.returncode == 0

            # Get runs to find run ID
            runs_result = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            runs = _extract_json_array(runs_result.stdout)
            run_id = runs[0]["id"]

            # Get single run detail
            get_result = _run_cli(["runs", "get", run_id], env=env)
            assert get_result.returncode == 0, f"Get run failed: {get_result.stderr}"

            run = _extract_json_object(get_result.stdout)
            assert "task_outcome" in run, f"Run detail missing task_outcome: {run.keys()}"
            # task_outcome_reason may be null, but field should exist
            assert "task_outcome_reason" in run or run.get("task_outcome") != "failed", \
                "FAILED outcome should have task_outcome_reason field"


# === E2E Tests: Task Outcome Persistence ===

class TestTaskOutcomePersistence:
    """E2E tests verifying task_outcome is persisted correctly."""

    def test_outcome_persists_across_cli_calls(self):
        """E2E: task_outcome value persists when retrieved via separate CLI call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "Persistence Test",
                "--prompt", "Test",
                "--project", tmpdir,
                "--cron", "0 0 1 1 *",
                "--model", "sonnet",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            # Trigger
            _run_cli(["tasks", "trigger", task_id], env=env)

            # Get runs - first call
            runs_result_1 = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            runs_1 = _extract_json_array(runs_result_1.stdout)
            outcome_1 = runs_1[0]["task_outcome"]

            # Get runs - second call (verifies DB persistence)
            runs_result_2 = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            runs_2 = _extract_json_array(runs_result_2.stdout)
            outcome_2 = runs_2[0]["task_outcome"]

            assert outcome_1 == outcome_2, "task_outcome should persist across CLI calls"


# === E2E Tests: Task Outcome Parsing ===

class TestTaskOutcomeSuccessParsing:
    """E2E tests verifying SUCCESS task outcome is correctly parsed and stored."""

    def test_task_with_success_marker_has_success_outcome(self):
        """E2E: Task that outputs TASK_STATUS: SUCCESS has task_outcome='success'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a task with a prompt that will make Claude output SUCCESS
            success_prompt = """Your task is to output exactly these two lines and nothing else:

Task complete.

TASK_STATUS: SUCCESS"""

            create_result = _run_cli([
                "tasks", "create",
                "--name", "Success Outcome Test",
                "--prompt", success_prompt,
                "--project", tmpdir,
                "--cron", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "120",
                "--disabled",
            ])

            assert create_result.returncode == 0, f"Create failed: {create_result.stderr}"
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            try:
                # Trigger the task
                trigger_result = _run_cli(["tasks", "trigger", task_id])
                assert trigger_result.returncode == 0, f"Trigger failed: {trigger_result.stderr}"

                # Get runs and verify task_outcome is 'success'
                runs_result = _run_cli(["runs", "list", "--task-id", task_id])
                assert runs_result.returncode == 0, f"List runs failed: {runs_result.stderr}"

                runs = _extract_json_array(runs_result.stdout)
                assert len(runs) >= 1, "Expected at least one run"

                run = runs[0]
                assert run["task_outcome"] == "success", \
                    f"Expected task_outcome='success', got '{run['task_outcome']}'. Output: {run.get('output', '')[:500]}"
            finally:
                # Clean up: delete the test task
                _run_cli(["tasks", "delete", task_id, "--force"])


class TestTaskOutcomeFailedParsing:
    """E2E tests verifying FAILED task outcome is correctly parsed and stored."""

    def test_task_with_failed_marker_has_failed_outcome(self):
        """E2E: Task that outputs TASK_STATUS: FAILED has task_outcome='failed' with reason."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a task with a prompt that will make Claude output FAILED
            failed_prompt = """Your task is to output exactly these two lines and nothing else:

I cannot complete this task.

TASK_STATUS: FAILED - Test failure reason"""

            create_result = _run_cli([
                "tasks", "create",
                "--name", "Failed Outcome Test",
                "--prompt", failed_prompt,
                "--project", tmpdir,
                "--cron", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "120",
                "--disabled",
            ])

            assert create_result.returncode == 0, f"Create failed: {create_result.stderr}"
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            try:
                # Trigger the task
                trigger_result = _run_cli(["tasks", "trigger", task_id])
                assert trigger_result.returncode == 0, f"Trigger failed: {trigger_result.stderr}"

                # Get runs and verify task_outcome is 'failed' with reason
                runs_result = _run_cli(["runs", "list", "--task-id", task_id])
                assert runs_result.returncode == 0, f"List runs failed: {runs_result.stderr}"

                runs = _extract_json_array(runs_result.stdout)
                assert len(runs) >= 1, "Expected at least one run"

                run = runs[0]
                assert run["task_outcome"] == "failed", \
                    f"Expected task_outcome='failed', got '{run['task_outcome']}'. Output: {run.get('output', '')[:500]}"

                # Verify reason is captured (get full run details)
                run_detail_result = _run_cli(["runs", "get", run["id"]])
                assert run_detail_result.returncode == 0
                run_detail = _extract_json_object(run_detail_result.stdout)

                assert run_detail.get("task_outcome_reason") is not None, \
                    f"Expected task_outcome_reason to be set for failed task. Got: {run_detail}"
                assert "Test failure reason" in run_detail["task_outcome_reason"], \
                    f"Expected reason to contain 'Test failure reason', got: {run_detail['task_outcome_reason']}"
            finally:
                # Clean up: delete the test task
                _run_cli(["tasks", "delete", task_id, "--force"])
