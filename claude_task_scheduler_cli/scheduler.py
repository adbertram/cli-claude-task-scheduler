"""Scheduler service using APScheduler for task execution."""

import os
import re
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter

from .db_client import DatabaseClient
from .models.task import ScheduledTask, TaskRun, TaskStatus
from .notifications import NotificationService


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

        # Load all enabled tasks
        self._load_enabled_tasks()

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None
            self._start_time = None

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
        """Load all enabled tasks into the scheduler."""
        tasks = self.db_client.list_tasks(enabled_only=True)
        for task in tasks:
            self.add_job(task)

    def add_job(self, task: ScheduledTask) -> None:
        """Add a task to the scheduler."""
        if self._scheduler is None:
            return

        # Remove existing job if present
        try:
            self._scheduler.remove_job(task.id)
        except Exception:
            pass

        # Parse cron expression
        trigger = CronTrigger.from_crontab(task.cron_expression)

        # Add job
        self._scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=task.id,
            args=[task.id],
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

        # Execute directly (scheduler handles this)
        return self._execute_task(task_id)

    def _execute_task(self, task_id: str, attempt_number: int = 1) -> Optional[TaskRun]:
        """Execute a scheduled task.

        Args:
            task_id: ID of the task to execute
            attempt_number: Current attempt number (for retries)

        Returns:
            TaskRun record or None if task not found
        """
        task = self.db_client.get_task(task_id)
        if not task:
            return None

        # Create run record
        run = self.db_client.create_run(task_id, attempt_number)

        # Send start notification
        if self._notification_service:
            self._notification_service.notify_start(task, run)

        try:
            # Execute Claude Code
            result = self._invoke_claude(task)

            # Update run with results
            status = TaskStatus.COMPLETED if result["exit_code"] == 0 else TaskStatus.FAILED
            run = self.db_client.update_run(
                run.id,
                status=status,
                session_id=result.get("session_id"),
                exit_code=result["exit_code"],
                error_message=result.get("error"),
                summary=result.get("summary"),
                completed_at=datetime.utcnow(),
            )

            # Send notification
            if self._notification_service:
                if status == TaskStatus.COMPLETED:
                    self._notification_service.notify_success(task, run)
                else:
                    self._notification_service.notify_error(task, run)

            # Handle retry on failure
            if status == TaskStatus.FAILED and attempt_number < task.max_retries:
                self._schedule_retry(task, attempt_number + 1)

        except Exception as e:
            # Update run with error
            run = self.db_client.update_run(
                run.id,
                status=TaskStatus.FAILED,
                error_message=str(e),
                completed_at=datetime.utcnow(),
            )

            # Send error notification
            if self._notification_service:
                self._notification_service.notify_error(task, run)

            # Handle retry
            if attempt_number < task.max_retries:
                self._schedule_retry(task, attempt_number + 1)

        return run

    def _invoke_claude(self, task: ScheduledTask) -> dict:
        """Invoke Claude Code CLI.

        Args:
            task: The task to execute

        Returns:
            Dict with exit_code, session_id, summary, error
        """
        cmd = [
            "claude",
            "--print",
            "--model", task.model,
            "--output-format", "json",
        ]

        try:
            result = subprocess.run(
                cmd,
                input=task.prompt,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                cwd=task.project_path,
            )

            # Try to parse session ID from output
            session_id = self._extract_session_id(result.stdout)

            # Generate summary from output (first 500 chars)
            summary = self._generate_summary(result.stdout, result.stderr)

            return {
                "exit_code": result.returncode,
                "session_id": session_id,
                "summary": summary,
                "error": result.stderr if result.returncode != 0 else None,
            }

        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "error": "Task execution timed out after 1 hour",
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "error": str(e),
            }

    def _extract_session_id(self, output: str) -> Optional[str]:
        """Extract session ID from Claude output."""
        # Look for session ID pattern in output
        # Format varies but typically includes session identifier
        match = re.search(r'session[_-]?id["\s:]+([a-f0-9-]+)', output, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _generate_summary(self, stdout: str, stderr: str) -> str:
        """Generate a brief summary of the output."""
        output = stdout or stderr or "No output"
        # Take first 500 chars
        if len(output) > 500:
            return output[:500] + "..."
        return output

    def _schedule_retry(self, task: ScheduledTask, next_attempt: int) -> None:
        """Schedule a retry with exponential backoff.

        Args:
            task: Task to retry
            next_attempt: Attempt number for the retry
        """
        # Exponential backoff: 1min, 2min, 4min, 8min, etc.
        delay_seconds = 60 * (2 ** (next_attempt - 1))

        if self._scheduler is not None:
            self._scheduler.add_job(
                self._execute_task,
                "date",
                run_date=datetime.utcnow().timestamp() + delay_seconds,
                id=f"{task.id}_retry_{next_attempt}",
                args=[task.id, next_attempt],
            )

    def get_next_run_time(self, cron_expression: str) -> Optional[datetime]:
        """Get next run time for a cron expression."""
        try:
            cron = croniter(cron_expression, datetime.utcnow())
            return cron.get_next(datetime)
        except Exception:
            return None

    def validate_cron(self, cron_expression: str) -> bool:
        """Validate a cron expression."""
        try:
            croniter(cron_expression)
            return True
        except Exception:
            return False
