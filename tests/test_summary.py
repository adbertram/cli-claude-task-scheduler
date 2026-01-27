"""Unit tests for SummaryService and spawn_summary_generation.

Tests use direct Python imports and mocking - no CLI subprocess calls.
"""

import json
import subprocess
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock, call

import pytest

from claude_task_scheduler_cli.summary import (
    SummaryService,
    spawn_summary_generation,
    SUMMARY_PROMPT,
    SUMMARY_TIMEOUT_SECONDS,
)
from claude_task_scheduler_cli.models.task import ScheduledTask, TaskRun, RunStatus, TaskOutcome
from claude_task_scheduler_cli.models.log import TaskLog, LogEventType, LogLevel


# === Fixtures ===

@pytest.fixture
def mock_db_client():
    """Create a mock DatabaseClient."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_task():
    """Create a sample ScheduledTask."""
    return ScheduledTask(
        id="task-123",
        name="Test Task",
        prompt="Do something",
        project_path="/tmp/test-project",
        model="opus",
        summary_model="opus",
        max_retries=3,
        timeout_seconds=3600,
        enabled=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_run():
    """Create a sample TaskRun."""
    return TaskRun(
        id="run-456",
        task_id="task-123",
        status=RunStatus.SUCCESS,
        started_at=datetime.utcnow(),
        output="Task completed successfully",
        attempt_number=1,
        task_outcome=TaskOutcome.SUCCESS,
    )


@pytest.fixture
def sample_logs():
    """Create sample log entries."""
    now = datetime.utcnow()
    return [
        TaskLog(
            id="log-1",
            task_id="task-123",
            run_id="run-456",
            event_type=LogEventType.TASK_START,
            level=LogLevel.INFO,
            message="Task started",
            details=None,
            created_at=now,
        ),
        TaskLog(
            id="log-2",
            task_id="task-123",
            run_id="run-456",
            event_type=LogEventType.CLAUDE_RESPONSE,
            level=LogLevel.INFO,
            message="Claude response",
            details='{"text": "I completed the task."}',
            created_at=now,
        ),
        TaskLog(
            id="log-3",
            task_id="task-123",
            run_id="run-456",
            event_type=LogEventType.TASK_COMPLETE,
            level=LogLevel.INFO,
            message="Task completed successfully",
            details=None,
            created_at=now,
        ),
    ]


# === SummaryService.generate_summary Tests ===

class TestSummaryServiceGenerateSummary:
    """Tests for SummaryService.generate_summary() method."""

    def test_generate_summary_success(self, mock_db_client, sample_task, sample_run, sample_logs):
        """Test successful summary generation."""
        # Setup mocks
        mock_db_client.get_run.return_value = sample_run
        mock_db_client.get_task.return_value = sample_task
        mock_db_client.list_logs.return_value = sample_logs

        # Mock subprocess for Claude invocation
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            '[{"type": "result", "result": "Summary: Task completed successfully"}]',
            ""
        )
        mock_process.returncode = 0

        with patch.object(SummaryService, '__init__', lambda self, db_path: None):
            service = SummaryService.__new__(SummaryService)
            service.db_path = "/tmp/test.db"
            service.db_client = mock_db_client

            with patch('subprocess.Popen', return_value=mock_process):
                service.generate_summary("run-456")

        # Verify db_client.update_run was called with summary
        mock_db_client.update_run.assert_called_once()
        call_args = mock_db_client.update_run.call_args
        assert call_args[0][0] == "run-456"
        assert "Summary: Task completed successfully" in call_args[1]["run_summary"]

    def test_generate_summary_timeout(self, mock_db_client, sample_task, sample_run, sample_logs):
        """Test summary generation handles timeout."""
        mock_db_client.get_run.return_value = sample_run
        mock_db_client.get_task.return_value = sample_task
        mock_db_client.list_logs.return_value = sample_logs

        mock_process = MagicMock()
        mock_process.communicate.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=60)
        mock_process.kill = MagicMock()
        mock_process.wait = MagicMock()

        with patch.object(SummaryService, '__init__', lambda self, db_path: None):
            service = SummaryService.__new__(SummaryService)
            service.db_path = "/tmp/test.db"
            service.db_client = mock_db_client

            with patch('subprocess.Popen', return_value=mock_process):
                service.generate_summary("run-456")

        # Verify error message stored
        mock_db_client.update_run.assert_called_once()
        call_args = mock_db_client.update_run.call_args
        assert "timed out" in call_args[1]["run_summary"].lower()

    def test_generate_summary_subprocess_error(self, mock_db_client, sample_task, sample_run, sample_logs):
        """Test summary generation handles subprocess error."""
        mock_db_client.get_run.return_value = sample_run
        mock_db_client.get_task.return_value = sample_task
        mock_db_client.list_logs.return_value = sample_logs

        mock_process = MagicMock()
        mock_process.communicate.return_value = ("", "Error: API failure")
        mock_process.returncode = 1

        with patch.object(SummaryService, '__init__', lambda self, db_path: None):
            service = SummaryService.__new__(SummaryService)
            service.db_path = "/tmp/test.db"
            service.db_client = mock_db_client

            with patch('subprocess.Popen', return_value=mock_process):
                service.generate_summary("run-456")

        # Verify error message stored
        mock_db_client.update_run.assert_called_once()
        call_args = mock_db_client.update_run.call_args
        assert "failed" in call_args[1]["run_summary"].lower()

    def test_generate_summary_run_not_found(self, mock_db_client):
        """Test summary generation when run not found."""
        mock_db_client.get_run.return_value = None

        with patch.object(SummaryService, '__init__', lambda self, db_path: None):
            service = SummaryService.__new__(SummaryService)
            service.db_path = "/tmp/test.db"
            service.db_client = mock_db_client

            service.generate_summary("nonexistent-run")

        # Should not call update_run
        mock_db_client.update_run.assert_not_called()

    def test_generate_summary_task_not_found(self, mock_db_client, sample_run):
        """Test summary generation when task not found."""
        mock_db_client.get_run.return_value = sample_run
        mock_db_client.get_task.return_value = None

        with patch.object(SummaryService, '__init__', lambda self, db_path: None):
            service = SummaryService.__new__(SummaryService)
            service.db_path = "/tmp/test.db"
            service.db_client = mock_db_client

            service.generate_summary("run-456")

        # Should store error message
        mock_db_client.update_run.assert_called_once()
        call_args = mock_db_client.update_run.call_args
        assert "task not found" in call_args[1]["run_summary"].lower()

    def test_generate_summary_no_logs(self, mock_db_client, sample_task, sample_run):
        """Test summary generation when no logs exist."""
        mock_db_client.get_run.return_value = sample_run
        mock_db_client.get_task.return_value = sample_task
        mock_db_client.list_logs.return_value = []

        with patch.object(SummaryService, '__init__', lambda self, db_path: None):
            service = SummaryService.__new__(SummaryService)
            service.db_path = "/tmp/test.db"
            service.db_client = mock_db_client

            service.generate_summary("run-456")

        # Should store "no logs" message
        mock_db_client.update_run.assert_called_once()
        call_args = mock_db_client.update_run.call_args
        assert "no logs" in call_args[1]["run_summary"].lower()


# === spawn_summary_generation Tests ===

class TestSpawnSummaryGeneration:
    """Tests for spawn_summary_generation() function."""

    def test_spawn_creates_detached_subprocess(self, sample_task):
        """Test that spawn creates a detached subprocess."""
        with patch('subprocess.Popen') as mock_popen:
            spawn_summary_generation("run-456", sample_task, "/tmp/test.db")

            mock_popen.assert_called_once()
            call_args = mock_popen.call_args

            # Verify start_new_session=True for detachment
            assert call_args[1].get("start_new_session") is True

            # Verify stdout/stderr are DEVNULL
            assert call_args[1].get("stdout") is subprocess.DEVNULL
            assert call_args[1].get("stderr") is subprocess.DEVNULL

    def test_spawn_uses_python_executable(self, sample_task):
        """Test that spawn uses the current Python executable."""
        with patch('subprocess.Popen') as mock_popen:
            spawn_summary_generation("run-456", sample_task, "/tmp/test.db")

            call_args = mock_popen.call_args[0][0]  # First positional arg is the command list

            # First element should be sys.executable
            assert call_args[0] == sys.executable
            assert call_args[1] == "-c"

    def test_spawn_passes_correct_run_id(self, sample_task):
        """Test that spawn passes the correct run_id in the command."""
        with patch('subprocess.Popen') as mock_popen:
            spawn_summary_generation("run-456", sample_task, "/tmp/test.db")

            call_args = mock_popen.call_args[0][0]
            command_string = call_args[2]  # The -c argument

            assert "run-456" in command_string
            assert "SummaryService" in command_string
            assert "generate_summary" in command_string

    def test_spawn_returns_immediately(self, sample_task):
        """Test that spawn returns without waiting for subprocess."""
        mock_process = MagicMock()

        with patch('subprocess.Popen', return_value=mock_process) as mock_popen:
            # spawn should return immediately without calling wait() or communicate()
            spawn_summary_generation("run-456", sample_task, "/tmp/test.db")

            # Popen should be called but not wait()
            mock_popen.assert_called_once()
            mock_process.wait.assert_not_called()
            mock_process.communicate.assert_not_called()


# === Constants Tests ===

class TestSummaryConstants:
    """Tests for summary module constants."""

    def test_summary_timeout_is_60_seconds(self):
        """Verify the hardcoded 60 second timeout."""
        assert SUMMARY_TIMEOUT_SECONDS == 60

    def test_summary_prompt_starts_with_instruction(self):
        """Verify the summary prompt has correct format."""
        assert "Summarize" in SUMMARY_PROMPT
        assert "logs" in SUMMARY_PROMPT.lower()
