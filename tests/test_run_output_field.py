"""E2E tests for task run output field.

Verifies that:
1. Run records have 'output' field (not 'summary')
2. Output is NOT truncated (doesn't end with '...')
3. All expected fields are present
4. Timestamps are in local time, not UTC
"""

import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone

import pytest


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
    clean_output = ansi_escape.sub('', output)

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


class TestRunOutputField:
    """E2E tests for run output field."""

    def test_run_has_output_field_not_summary(self):
        """Run record must have 'output' field, not 'summary'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "Output Field Test",
                "--prompt", "Say hello",
                "--project", tmpdir,
                "--schedule", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0, f"Create failed: {create_result.stderr}"
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            # Trigger task
            trigger_result = _run_cli(["tasks", "trigger", task_id], env=env)
            assert trigger_result.returncode == 0, f"Trigger failed: {trigger_result.stderr}"

            # Get runs
            runs_result = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            assert runs_result.returncode == 0, f"List runs failed: {runs_result.stderr}"

            runs = _extract_json_array(runs_result.stdout)
            assert len(runs) >= 1, "Expected at least 1 run"

            run = runs[0]

            # Verify 'output' field exists
            assert "output" in run, f"Run must have 'output' field. Fields: {list(run.keys())}"

            # Verify 'summary' field does NOT exist
            assert "summary" not in run, f"Run must NOT have 'summary' field. Fields: {list(run.keys())}"

    def test_run_output_not_truncated(self):
        """Run output must not be truncated (must not end with '...')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "Output Truncation Test",
                "--prompt", "Say hello",
                "--project", tmpdir,
                "--schedule", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0, f"Create failed: {create_result.stderr}"
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            # Trigger task
            trigger_result = _run_cli(["tasks", "trigger", task_id], env=env)
            assert trigger_result.returncode == 0, f"Trigger failed: {trigger_result.stderr}"

            # Get runs
            runs_result = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            assert runs_result.returncode == 0

            runs = _extract_json_array(runs_result.stdout)
            assert len(runs) >= 1

            run = runs[0]
            output = run.get("output", "")

            # Output must not end with '...' (truncation indicator)
            assert not output.endswith("..."), f"Output appears truncated: {output[-100:]}"

    def test_run_has_all_expected_fields(self):
        """Run record must have all expected fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "All Fields Test",
                "--prompt", "Say hello",
                "--project", tmpdir,
                "--schedule", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            # Trigger task
            trigger_result = _run_cli(["tasks", "trigger", task_id], env=env)
            assert trigger_result.returncode == 0

            # Get runs
            runs_result = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            assert runs_result.returncode == 0

            runs = _extract_json_array(runs_result.stdout)
            assert len(runs) >= 1

            run = runs[0]

            # Verify all expected fields exist
            expected_fields = [
                "id",
                "task_id",
                "status",
                "started_at",
                "completed_at",
                "session_id",
                "exit_code",
                "error_message",
                "output",
                "attempt_number",
            ]

            for field in expected_fields:
                assert field in run, f"Run missing field '{field}'. Fields: {list(run.keys())}"

            # Verify task_id matches
            assert run["task_id"] == task_id

            # Verify status is valid
            valid_statuses = ["running", "success", "failure", "timeout"]
            assert run["status"] in valid_statuses, f"Invalid status: {run['status']}"

    def test_run_timestamps_are_local_time(self):
        """Run timestamps must be in local time, not UTC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Calculate timezone offset (local - UTC)
            utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
            local_now = datetime.now()
            tz_offset_seconds = (local_now - utc_now).total_seconds()

            # Skip test if timezone offset is less than 1 hour (can't reliably distinguish)
            if abs(tz_offset_seconds) < 3600:
                pytest.skip("Timezone offset too small to reliably test local vs UTC")

            # Create task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "Local Time Test",
                "--prompt", "Say hello",
                "--project", tmpdir,
                "--schedule", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0
            task = _extract_json_object(create_result.stdout)
            task_id = task["id"]

            # Trigger task
            trigger_result = _run_cli(["tasks", "trigger", task_id], env=env)
            assert trigger_result.returncode == 0

            # Get runs
            runs_result = _run_cli(["runs", "list", "--task-id", task_id], env=env)
            assert runs_result.returncode == 0

            runs = _extract_json_array(runs_result.stdout)
            assert len(runs) >= 1

            run = runs[0]
            started_at_str = run.get("started_at", "")

            # Parse the timestamp from output
            # Format: "2026-01-26 13:01:10.692984"
            started_at = datetime.strptime(started_at_str, "%Y-%m-%d %H:%M:%S.%f")

            # Tolerance for test execution time
            tolerance_seconds = 120

            # Verify timestamp is close to LOCAL time
            diff_from_local = abs((started_at - local_now).total_seconds())
            assert diff_from_local < tolerance_seconds, (
                f"Timestamp not close to local time. "
                f"started_at={started_at}, local_now={local_now}, diff={diff_from_local}s"
            )

            # Verify timestamp is NOT close to UTC time (should differ by timezone offset)
            diff_from_utc = abs((started_at - utc_now).total_seconds())
            assert diff_from_utc > (abs(tz_offset_seconds) - tolerance_seconds), (
                f"Timestamp appears to be UTC, not local time. "
                f"started_at={started_at}, utc_now={utc_now}, diff_from_utc={diff_from_utc}s, "
                f"expected_offset={abs(tz_offset_seconds)}s"
            )
