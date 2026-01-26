"""Scheduler service using APScheduler for task execution."""

import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter

from .db_client import DatabaseClient
from .health import get_socket_path
from .logger import LoggerService
from .models.task import ScheduledTask, TaskRun, RunStatus, TaskOutcome
from .notifications import NotificationService

# Base prompt prepended to all scheduled tasks to enforce non-interactive behavior
BASE_PROMPT = """You are in a non-interactive environment. If you are requested to perform any user-interactive task or if you need feedback in any way from the user, you must stop immediately and report it.

IMPORTANT: At the END of your response, you MUST include a task status marker:
- If you completed the task: TASK_STATUS: SUCCESS
- If you could not complete the task: TASK_STATUS: FAILED - brief reason

"""


def parse_task_outcome(output: str) -> tuple[TaskOutcome, Optional[str]]:
    """Parse TASK_STATUS marker from Claude's response.

    Extracts the semantic task outcome from Claude's output. The marker can be:
    - TASK_STATUS: SUCCESS
    - TASK_STATUS: FAILED - reason

    Args:
        output: The raw output from Claude (may be JSON or plain text)

    Returns:
        Tuple of (TaskOutcome, reason). Reason is only present for FAILED status.
    """
    if not output:
        return TaskOutcome.UNKNOWN, None

    # Try to extract from JSON result if present (Claude's --output-format json)
    try:
        data = json.loads(output)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("type") == "result":
                    output = item.get("result", "")
                    break
    except (json.JSONDecodeError, TypeError):
        pass

    # Regex: TASK_STATUS: SUCCESS or TASK_STATUS: FAILED - reason
    pattern = r'TASK_STATUS:\s*(SUCCESS|FAILED)(?:\s*-\s*(.+?))?(?:\n|$)'
    match = re.search(pattern, output, re.IGNORECASE)

    if not match:
        return TaskOutcome.UNKNOWN, None

    status = match.group(1).upper()
    reason = match.group(2).strip() if match.group(2) else None

    if status == "SUCCESS":
        return TaskOutcome.SUCCESS, None
    elif status == "FAILED":
        return TaskOutcome.FAILED, reason

    return TaskOutcome.UNKNOWN, None


def execute_scheduled_task(task_id: str, db_path: str, attempt_number: int = 1) -> Optional[TaskRun]:
    """Module-level function for APScheduler job execution.

    This is a standalone function (not a method) because APScheduler's SQLAlchemyJobStore
    pickles jobs for persistence. Instance methods would pickle the entire object,
    including SQLAlchemy engines which can't be pickled.

    Args:
        task_id: ID of the task to execute
        db_path: Path to the SQLite database
        attempt_number: Current attempt number (for retries)

    Returns:
        TaskRun record or None if task not found
    """
    # Create fresh clients for this execution
    db_client = DatabaseClient(db_path)
    notification_service = NotificationService(db_client)
    logger_service = LoggerService(db_client)

    task = db_client.get_task(task_id)
    if not task:
        return None

    # Create run record
    run = db_client.create_run(task_id, attempt_number)

    # Log task start
    logger_service.log_task_start(task, run)

    # Send start notification
    notification_service.notify_start(task, run)

    try:
        # Execute Claude Code
        result = _invoke_claude_standalone(task, run, logger_service)

        # Update run with results
        if result["exit_code"] == 0:
            status = RunStatus.SUCCESS
        elif result.get("timed_out"):
            status = RunStatus.TIMEOUT
        else:
            status = RunStatus.FAILURE

        # Parse semantic task outcome from Claude's response
        task_outcome, task_outcome_reason = parse_task_outcome(result.get("output", ""))

        db_client.update_run(
            run.id,
            status=status,
            session_id=result.get("session_id"),
            exit_code=result["exit_code"],
            error_message=result.get("error"),
            output=result.get("output"),
            completed_at=datetime.utcnow(),
            task_outcome=task_outcome,
            task_outcome_reason=task_outcome_reason,
        )
        # Update local run object for logging/notifications
        run.status = status
        run.exit_code = result["exit_code"]
        run.error_message = result.get("error")
        run.output = result.get("output")
        run.task_outcome = task_outcome
        run.task_outcome_reason = task_outcome_reason

        # Log completion or failure
        if status == RunStatus.SUCCESS:
            logger_service.log_task_complete(
                task, run,
                stdout=result.get("stdout"),
                stderr=result.get("stderr"),
            )
        else:
            logger_service.log_task_failed(
                task, run,
                error=result.get("error", "Unknown error"),
                stdout=result.get("stdout"),
                stderr=result.get("stderr"),
            )

        # Send notification based on both process status and semantic outcome
        # A task that ran successfully (exit_code=0) but failed semantically should
        # still trigger an error notification
        if status == RunStatus.SUCCESS:
            if task_outcome == TaskOutcome.FAILED:
                notification_service.notify_error(task, run)  # Task failed semantically
            else:
                notification_service.notify_success(task, run)
        else:
            notification_service.notify_error(task, run)

        # Handle retry on failure or timeout
        if status in (RunStatus.FAILURE, RunStatus.TIMEOUT) and attempt_number < task.max_retries:
            _schedule_retry_standalone(task_id, db_path, attempt_number + 1, task, run, logger_service)

    except Exception as e:
        # Update run with error
        db_client.update_run(
            run.id,
            status=RunStatus.FAILURE,
            error_message=str(e),
            output=str(e),
            completed_at=datetime.utcnow(),
            task_outcome=TaskOutcome.FAILED,
            task_outcome_reason=str(e)[:200],
        )
        # Update local run object for logging/notifications
        run.status = RunStatus.FAILURE
        run.output = str(e)[:500]
        run.error_message = str(e)
        run.task_outcome = TaskOutcome.FAILED
        run.task_outcome_reason = str(e)[:200]

        # Log failure
        logger_service.log_task_failed(task, run, error=str(e))

        # Send error notification
        notification_service.notify_error(task, run)

        # Handle retry
        if attempt_number < task.max_retries:
            _schedule_retry_standalone(task_id, db_path, attempt_number + 1, task, run, logger_service)

    return run


def _invoke_claude_standalone(task: ScheduledTask, run: TaskRun, logger_service: LoggerService) -> dict:
    """Invoke Claude Code CLI (standalone version).

    Args:
        task: The task to execute
        run: The run record for logging
        logger_service: Logger service for output capture

    Returns:
        Dict with exit_code, session_id, output, error, stdout, stderr
    """
    cmd = [
        "claude",
        "--print",
        "--model", task.model,
        "--output-format", "json",
    ]

    # Prepend non-interactive base prompt to enforce explicit failure on user interaction
    full_prompt = BASE_PROMPT + task.prompt

    # Log command execution
    logger_service.log_command_executed(task, run, cmd, task.project_path)

    try:
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=task.timeout_seconds,
            cwd=task.project_path,
        )

        # Log output captured (full output, no truncation)
        logger_service.log_output_captured(
            task, run,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
        )

        # Try to parse session ID from output
        session_id = None
        match = re.search(r'session[_-]?id["\s:]+([a-f0-9-]+)', result.stdout, re.IGNORECASE)
        if match:
            session_id = match.group(1)

        # Capture full output
        full_output = result.stdout or result.stderr or ""
        if not full_output:
            full_output = "Completed with no output" if result.returncode == 0 else "Failed with no output"

        return {
            "exit_code": result.returncode,
            "session_id": session_id,
            "output": full_output,
            "error": result.stderr if result.returncode != 0 else None,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except subprocess.TimeoutExpired:
        timeout_msg = f"Task execution timed out after {task.timeout_seconds} seconds"
        return {
            "exit_code": -1,
            "error": timeout_msg,
            "output": timeout_msg,
            "stdout": None,
            "stderr": None,
            "timed_out": True,
        }
    except Exception as e:
        error_msg = str(e)
        return {
            "exit_code": -1,
            "error": error_msg,
            "output": error_msg,
            "stdout": None,
            "stderr": None,
            "timed_out": False,
        }


def _schedule_retry_standalone(
    task_id: str,
    db_path: str,
    next_attempt: int,
    task: ScheduledTask,
    run: TaskRun,
    logger_service: LoggerService,
) -> int:
    """Schedule a retry with exponential backoff (standalone version).

    This creates a one-shot job in a temporary scheduler just for the retry.

    Args:
        task_id: Task to retry
        db_path: Path to database
        next_attempt: Attempt number for the retry
        task: Task object (for logging)
        run: Run object (for logging)
        logger_service: Logger for recording retry

    Returns:
        Delay in seconds before retry
    """
    # Smart backoff: exponential base, but cap at half the timeout for TIMEOUT status
    base_delay = 60 * (2 ** (next_attempt - 1))

    # If the last run timed out, cap retry delay at half the timeout duration
    # This prevents waiting longer than the task itself takes to fail
    if run.status == RunStatus.TIMEOUT:
        max_delay = max(60, task.timeout_seconds // 2)
        delay_seconds = min(base_delay, max_delay)
    else:
        delay_seconds = base_delay

    # Log the retry
    logger_service.log_task_retry(task, run, next_attempt, delay_seconds)

    # Schedule via subprocess to avoid needing scheduler instance
    # The retry will be picked up when scheduler restarts or via direct execution
    # For now, use a simple thread with sleep
    def delayed_retry():
        time.sleep(delay_seconds)
        execute_scheduled_task(task_id, db_path, next_attempt)

    retry_thread = threading.Thread(target=delayed_retry, daemon=True)
    retry_thread.start()

    return delay_seconds


class SchedulerService:
    """Service for scheduling and executing Claude Code tasks."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the scheduler service.

        Args:
            db_path: Optional path to SQLite database.
        """
        self.db_client = DatabaseClient(db_path)
        self._db_path = db_path or self._get_default_db_path()
        self._scheduler: Optional[BackgroundScheduler] = None
        self._start_time: Optional[datetime] = None
        self._notification_service = NotificationService(self.db_client)
        self._logger_service = LoggerService(self.db_client)
        self._health_server: Optional[socketserver.UnixStreamServer] = None
        self._health_thread: Optional[threading.Thread] = None

    def _get_default_db_path(self) -> str:
        """Get default database path."""
        db_dir = os.path.expanduser("~/.claude-task-scheduler")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "scheduler.db")

    def _create_scheduler(self) -> BackgroundScheduler:
        """Create APScheduler instance with SQLite job store."""
        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{self._db_path}")
        }
        executors = {
            "default": ThreadPoolExecutor(max_workers=10)
        }
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,  # 1 hour grace time for missed jobs
        }
        return BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="UTC",
        )

    def start(self) -> None:
        """Start the scheduler."""
        if self._scheduler is not None:
            return

        self._scheduler = self._create_scheduler()
        self._scheduler.start()
        self._start_time = datetime.utcnow()

        # Start the health check server
        self._start_health_server()

        # Load all enabled tasks
        self._load_enabled_tasks()

    def stop(self) -> None:
        """Stop the scheduler."""
        # Stop the health check server first
        self._stop_health_server()

        if self._scheduler is not None:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None
            self._start_time = None

    def _start_health_server(self) -> None:
        """Start Unix socket health server for daemon status checks."""
        socket_path = get_socket_path()

        # Clean up stale socket file
        if socket_path.exists():
            socket_path.unlink()

        # Ensure directory exists
        socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Reference to self for use in handler
        scheduler_service = self

        class HealthHandler(http.server.BaseHTTPRequestHandler):
            """HTTP handler for health check requests."""

            def log_message(self, format, *args):
                """Suppress request logging."""
                pass

            def do_GET(self):
                """Handle GET requests."""
                if self.path == "/health":
                    uptime = scheduler_service.get_uptime_seconds()
                    health = {
                        "running": True,
                        "uptime_seconds": int(uptime) if uptime else 0,
                        "job_count": scheduler_service.get_job_count(),
                        "pid": os.getpid(),
                    }
                    response = json.dumps(health).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                else:
                    self.send_error(404, "Not Found")

        class UnixSocketHTTPServer(socketserver.UnixStreamServer):
            """HTTP server using Unix socket."""

            def get_request(self):
                """Get the request and client address."""
                request, _ = super().get_request()
                return request, ("unix-socket", 0)

        self._health_server = UnixSocketHTTPServer(str(socket_path), HealthHandler)
        self._health_thread = threading.Thread(
            target=self._health_server.serve_forever,
            daemon=True,
            name="health-server",
        )
        self._health_thread.start()

    def _stop_health_server(self) -> None:
        """Stop the health check server and clean up socket file."""
        if self._health_server is not None:
            self._health_server.shutdown()
            self._health_server.server_close()
            self._health_server = None
            self._health_thread = None

        # Clean up socket file
        socket_path = get_socket_path()
        if socket_path.exists():
            socket_path.unlink()

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._scheduler is not None and self._scheduler.running

    def get_uptime_seconds(self) -> Optional[float]:
        """Get scheduler uptime in seconds."""
        if self._start_time is None:
            return None
        return (datetime.utcnow() - self._start_time).total_seconds()

    def get_job_count(self) -> int:
        """Get number of scheduled jobs."""
        if self._scheduler is None:
            return 0
        return len(self._scheduler.get_jobs())

    def get_next_runs(self, limit: int = 10) -> list[dict]:
        """Get next scheduled runs."""
        if self._scheduler is None:
            return []

        jobs = self._scheduler.get_jobs()
        next_runs = []
        for job in jobs[:limit]:
            next_run = job.next_run_time
            if next_run:
                next_runs.append({
                    "task_id": job.id,
                    "next_run_at": next_run.isoformat(),
                })
        return next_runs

    def _load_enabled_tasks(self) -> None:
        """Load all enabled tasks with schedules into the scheduler.

        Tasks without cron expressions are skipped - they can only be run manually.
        """
        tasks = self.db_client.list_tasks(enabled_only=True)
        for task in tasks:
            if task.cron_expression:
                self.add_job(task)

    def add_job(self, task: ScheduledTask) -> None:
        """Add a task to the scheduler.

        Tasks without a cron expression are skipped - they can only be run manually.
        """
        if self._scheduler is None:
            return

        # Skip tasks without schedules - they can only be run manually
        if not task.cron_expression:
            return

        # Remove existing job if present
        try:
            self._scheduler.remove_job(task.id)
        except Exception:
            pass

        # Parse cron expression
        trigger = CronTrigger.from_crontab(task.cron_expression)

        # Add job using module-level function (picklable for SQLAlchemyJobStore)
        self._scheduler.add_job(
            execute_scheduled_task,
            trigger=trigger,
            id=task.id,
            args=[task.id, self._db_path],
            replace_existing=True,
        )

    def remove_job(self, task_id: str) -> None:
        """Remove a task from the scheduler."""
        if self._scheduler is None:
            return

        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass

    def run_job_now(self, task_id: str) -> Optional[TaskRun]:
        """Trigger a task to run immediately via the scheduler."""
        task = self.db_client.get_task(task_id)
        if not task:
            return None

        # Execute directly using the standalone function
        return execute_scheduled_task(task_id, self._db_path)

    def get_next_run_time(self, cron_expression: Optional[str]) -> Optional[datetime]:
        """Get next run time for a cron expression (local time).

        Returns None if cron_expression is None or invalid.
        """
        if not cron_expression:
            return None
        try:
            cron = croniter(cron_expression, datetime.now())
            return cron.get_next(datetime)
        except Exception:
            return None

    def validate_cron(self, cron_expression: Optional[str]) -> bool:
        """Validate a cron expression.

        Returns False if cron_expression is None or invalid.
        """
        if not cron_expression:
            return False
        try:
            croniter(cron_expression)
            return True
        except Exception:
            return False
