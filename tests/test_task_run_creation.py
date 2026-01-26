"""E2E tests for task run record creation.

These tests verify that running a task ALWAYS creates a task_runs record,
regardless of whether the task succeeds, fails, or times out.

All tests use the CLI only - no internal Python function calls.
"""

import json
import os
import re
import subprocess
import tempfile

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
    # Remove ANSI color codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', output)

    # Find JSON object
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
    # Remove ANSI color codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', output)

    # Find JSON array
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


class TestTaskRunCreationCLI:
    """E2E tests verifying task_runs records are always created via CLI."""

    def test_trigger_task_creates_run_record(self):
        """E2E: Triggering a task via CLI creates a task_run record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # 1. Create a task via CLI
            create_result = _run_cli([
                "tasks", "create",
                "--name", "E2E Run Creation Test",
                "--prompt", "Say hello",
                "--project", project_path,
                "--schedule", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0, f"Create failed: {create_result.stderr}"
            created_task = _extract_json_object(create_result.stdout)
            task_id = created_task["id"]

            # 2. List runs before trigger - should be empty
            runs_before_result = _run_cli([
                "runs", "list",
                "--task-id", task_id,
            ], env=env)

            assert runs_before_result.returncode == 0, f"List runs failed: {runs_before_result.stderr}"
            # Check if output indicates no runs or empty array
            if "No data" in runs_before_result.stdout or "[]" in runs_before_result.stdout:
                runs_before = []
            else:
                try:
                    runs_before = _extract_json_array(runs_before_result.stdout)
                except ValueError:
                    runs_before = []

            assert len(runs_before) == 0, f"No runs should exist before trigger, got: {runs_before}"

            # 3. Trigger the task via CLI
            trigger_result = _run_cli([
                "tasks", "trigger",
                task_id,
            ], env=env)

            assert trigger_result.returncode == 0, f"Trigger failed: {trigger_result.stderr}"

            # 4. List runs after trigger - should have exactly 1 run
            runs_after_result = _run_cli([
                "runs", "list",
                "--task-id", task_id,
            ], env=env)

            assert runs_after_result.returncode == 0, f"List runs failed: {runs_after_result.stderr}"

            # Should NOT be "No data" anymore
            assert "No data" not in runs_after_result.stdout, (
                f"Expected run record but got 'No data'. Full output:\n{runs_after_result.stdout}"
            )

            runs_after = _extract_json_array(runs_after_result.stdout)
            assert len(runs_after) == 1, f"Expected exactly 1 run record, got {len(runs_after)}"

            # Verify run record has required fields
            run = runs_after[0]
            assert run.get("id") is not None, "Run must have an ID"
            assert run.get("task_id") == task_id, "Run must reference correct task"
            assert run.get("started_at") is not None, "Run must have started_at timestamp"
            assert run.get("status") is not None, "Run must have a status"

    def test_multiple_triggers_create_multiple_runs(self):
        """E2E: Each task trigger via CLI creates a separate run record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = tmpdir
            env = os.environ.copy()
            env["HOME"] = tmpdir

            # Create a task
            create_result = _run_cli([
                "tasks", "create",
                "--name", "E2E Multiple Runs Test",
                "--prompt", "Say test",
                "--project", project_path,
                "--schedule", "0 0 1 1 *",
                "--model", "sonnet",
                "--timeout", "60",
                "--disabled",
            ], env=env)

            assert create_result.returncode == 0
            created_task = _extract_json_object(create_result.stdout)
            task_id = created_task["id"]

            # Trigger the task multiple times
            num_triggers = 3
            for i in range(num_triggers):
                trigger_result = _run_cli(["tasks", "trigger", task_id], env=env)
                assert trigger_result.returncode == 0, f"Trigger {i+1} failed: {trigger_result.stderr}"

            # List runs - should have exactly num_triggers runs
            runs_result = _run_cli([
                "runs", "list",
                "--task-id", task_id,
            ], env=env)

            assert runs_result.returncode == 0
            runs = _extract_json_array(runs_result.stdout)
            assert len(runs) == num_triggers, f"Expected {num_triggers} runs, got {len(runs)}"

            # Each run should have a unique ID
            run_ids = [r["id"] for r in runs]
            assert len(set(run_ids)) == num_triggers, "Each run must have a unique ID"
