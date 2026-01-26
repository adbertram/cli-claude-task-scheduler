"""Logger service for auditing task activity."""

import json
from typing import Optional

from .db_client import DatabaseClient
from .models.log import LogEventType, LogLevel, TaskLog
from .models.task import ScheduledTask, ScheduledTaskDetail, TaskRun


class LoggerService:
    """Service for logging task activity to the database."""

    def __init__(self, db_client: DatabaseClient):
        """Initialize the logger service.

        Args:
            db_client: Database client for persistence
        """
        self._db_client = db_client

    def log_task_start(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
    ) -> TaskLog:
        """Log the start of a task execution.

        Args:
            task: The task being executed
            run: The run record

        Returns:
            Created TaskLog entry
        """
        message = f"Task '{task.name}' started (attempt {run.attempt_number})"
        details = json.dumps({
            "task_id": task.id,
            "task_name": task.name,
            "run_id": run.id,
            "attempt_number": run.attempt_number,
            "project_path": task.project_path,
            "model": task.model,
            "cron_expression": task.cron_expression,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.TASK_START,
            level=LogLevel.INFO,
            message=message,
            details=details,
        )

    def log_task_complete(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ) -> TaskLog:
        """Log the successful completion of a task.

        Args:
            task: The task that completed
            run: The run record
            stdout: Full stdout output (not truncated)
            stderr: Full stderr output (not truncated)

        Returns:
            Created TaskLog entry
        """
        message = f"Task '{task.name}' completed successfully"
        details = json.dumps({
            "task_id": task.id,
            "task_name": task.name,
            "run_id": run.id,
            "attempt_number": run.attempt_number,
            "exit_code": run.exit_code,
            "session_id": run.session_id,
            "stdout": stdout,
            "stderr": stderr,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.TASK_COMPLETE,
            level=LogLevel.INFO,
            message=message,
            details=details,
        )

    def log_task_failed(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
        error: str,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ) -> TaskLog:
        """Log a task failure.

        Args:
            task: The task that failed
            run: The run record
            error: Error message
            stdout: Full stdout output (not truncated)
            stderr: Full stderr output (not truncated)

        Returns:
            Created TaskLog entry
        """
        message = f"Task '{task.name}' failed: {error[:100]}"
        if len(error) > 100:
            message += "..."

        details = json.dumps({
            "task_id": task.id,
            "task_name": task.name,
            "run_id": run.id,
            "attempt_number": run.attempt_number,
            "exit_code": run.exit_code,
            "error": error,
            "stdout": stdout,
            "stderr": stderr,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.TASK_FAILED,
            level=LogLevel.ERROR,
            message=message,
            details=details,
        )

    def log_task_retry(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        previous_run: TaskRun,
        next_attempt: int,
        delay_seconds: int,
    ) -> TaskLog:
        """Log a task retry being scheduled.

        Args:
            task: The task being retried
            previous_run: The previous failed run
            next_attempt: The attempt number for the retry
            delay_seconds: Delay before retry in seconds

        Returns:
            Created TaskLog entry
        """
        message = f"Task '{task.name}' retry scheduled (attempt {next_attempt} in {delay_seconds}s)"
        details = json.dumps({
            "task_id": task.id,
            "task_name": task.name,
            "previous_run_id": previous_run.id,
            "previous_attempt": previous_run.attempt_number,
            "next_attempt": next_attempt,
            "delay_seconds": delay_seconds,
            "max_retries": task.max_retries,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=previous_run.id,
            event_type=LogEventType.TASK_RETRY,
            level=LogLevel.WARNING,
            message=message,
            details=details,
        )

    def log_command_executed(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
        command: list[str],
        cwd: str,
    ) -> TaskLog:
        """Log the execution of a command.

        Args:
            task: The task executing the command
            run: The run record
            command: Command and arguments being executed
            cwd: Working directory for the command

        Returns:
            Created TaskLog entry
        """
        cmd_str = " ".join(command)
        message = f"Executing: {cmd_str[:80]}"
        if len(cmd_str) > 80:
            message += "..."

        details = json.dumps({
            "task_id": task.id,
            "run_id": run.id,
            "command": command,
            "cwd": cwd,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.COMMAND_EXECUTED,
            level=LogLevel.DEBUG,
            message=message,
            details=details,
        )

    def log_output_captured(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
        stdout: Optional[str],
        stderr: Optional[str],
        exit_code: int,
    ) -> TaskLog:
        """Log captured command output.

        Args:
            task: The task that produced the output
            run: The run record
            stdout: Full stdout output (not truncated)
            stderr: Full stderr output (not truncated)
            exit_code: Command exit code

        Returns:
            Created TaskLog entry
        """
        stdout_len = len(stdout) if stdout else 0
        stderr_len = len(stderr) if stderr else 0
        message = f"Output captured: stdout={stdout_len} bytes, stderr={stderr_len} bytes, exit_code={exit_code}"

        details = json.dumps({
            "task_id": task.id,
            "run_id": run.id,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_length": stdout_len,
            "stderr_length": stderr_len,
        }, indent=2)

        level = LogLevel.INFO if exit_code == 0 else LogLevel.WARNING

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.OUTPUT_CAPTURED,
            level=level,
            message=message,
            details=details,
        )

    def log(
        self,
        task_id: str,
        event_type: LogEventType,
        message: str,
        level: LogLevel = LogLevel.INFO,
        run_id: Optional[str] = None,
        details: Optional[str] = None,
    ) -> TaskLog:
        """Generic log method.

        Args:
            task_id: ID of the task
            event_type: Type of event being logged
            message: Log message
            level: Log severity level
            run_id: Optional run ID if log is associated with a run
            details: Optional full details (no truncation)

        Returns:
            Created TaskLog entry
        """
        return self._db_client.create_log(
            task_id=task_id,
            run_id=run_id,
            event_type=event_type,
            level=level,
            message=message,
            details=details,
        )
