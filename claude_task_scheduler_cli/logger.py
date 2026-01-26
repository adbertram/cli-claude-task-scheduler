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

    def log_turn_start(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
        turn_number: int,
        model: str,
    ) -> TaskLog:
        """Log the start of a new conversation turn.

        Args:
            task: The task being executed
            run: The run record
            turn_number: Sequential turn number (1-indexed)
            model: Model being used

        Returns:
            Created TaskLog entry
        """
        message = f"Turn {turn_number} started (model: {model})"
        details = json.dumps({
            "task_id": task.id,
            "run_id": run.id,
            "turn_number": turn_number,
            "model": model,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.TURN_START,
            level=LogLevel.DEBUG,
            message=message,
            details=details,
        )

    def log_claude_response(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
        turn_number: int,
        content: str,
        model: Optional[str] = None,
    ) -> TaskLog:
        """Log a Claude assistant response.

        Args:
            task: The task being executed
            run: The run record
            turn_number: Which turn this response belongs to
            content: The text content of the response
            model: Optional model identifier

        Returns:
            Created TaskLog entry
        """
        # Create summary message (truncated for display)
        preview = content[:100].replace("\n", " ")
        if len(content) > 100:
            preview += "..."
        message = f"[Turn {turn_number}] {preview}"

        details = json.dumps({
            "task_id": task.id,
            "run_id": run.id,
            "turn_number": turn_number,
            "content": content,
            "content_length": len(content),
            "model": model,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.CLAUDE_RESPONSE,
            level=LogLevel.INFO,
            message=message,
            details=details,
        )

    def log_tool_use(
        self,
        task: ScheduledTask | ScheduledTaskDetail,
        run: TaskRun,
        turn_number: int,
        tool_name: str,
        tool_input: dict,
    ) -> TaskLog:
        """Log a tool invocation by Claude.

        Args:
            task: The task being executed
            run: The run record
            turn_number: Which turn this tool use belongs to
            tool_name: Name of the tool being invoked
            tool_input: Tool input parameters

        Returns:
            Created TaskLog entry
        """
        # Create summary based on tool type
        if tool_name == "Read":
            summary = tool_input.get("file_path", "unknown file")
        elif tool_name == "Edit":
            summary = tool_input.get("file_path", "unknown file")
        elif tool_name == "Write":
            summary = tool_input.get("file_path", "unknown file")
        elif tool_name == "Bash":
            cmd = tool_input.get("command", "")
            summary = cmd[:50] + "..." if len(cmd) > 50 else cmd
        elif tool_name == "Glob":
            summary = tool_input.get("pattern", "")
        elif tool_name == "Grep":
            summary = tool_input.get("pattern", "")
        else:
            summary = str(tool_input)[:50]

        message = f"[Turn {turn_number}] Tool: {tool_name} - {summary}"

        details = json.dumps({
            "task_id": task.id,
            "run_id": run.id,
            "turn_number": turn_number,
            "tool_name": tool_name,
            "tool_input": tool_input,
        }, indent=2)

        return self._db_client.create_log(
            task_id=task.id,
            run_id=run.id,
            event_type=LogEventType.TOOL_USE,
            level=LogLevel.INFO,
            message=message,
            details=details,
        )
