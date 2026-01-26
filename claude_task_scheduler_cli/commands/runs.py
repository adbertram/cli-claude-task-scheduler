"""Task run management commands."""

from typing import Optional

import typer

from ..db_client import DatabaseClient
from ..models.task import RunStatus
from ..output import print_error, print_json, print_success, print_table
from ..scheduler import SchedulerService

app = typer.Typer(help="Manage task runs", no_args_is_help=True)


def _get_db_client() -> DatabaseClient:
    """Get database client."""
    return DatabaseClient()


def _get_scheduler() -> SchedulerService:
    """Get scheduler service."""
    return SchedulerService()


@app.command("list")
def list_runs(
    task_id: Optional[str] = typer.Option(None, "--task-id", "-t", help="Filter by task ID"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (running, success, failure, timeout)"),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum number of results"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
    filter: Optional[list[str]] = typer.Option(None, "--filter", "-f", help="Filter: field:op:value"),
    properties: Optional[str] = typer.Option(None, "--properties", "-p", help="Comma-separated list of fields"),
):
    """List task runs."""
    db_client = _get_db_client()

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = RunStatus(status.lower())
        except ValueError:
            print_error(f"Invalid status: {status}. Valid values: running, success, failure, timeout")
            raise typer.Exit(1)

    runs = db_client.list_runs(task_id=task_id, status=status_filter, limit=limit)

    if table:
        print_table(
            runs,
            ["id", "task_id", "status", "task_outcome", "started_at", "completed_at", "attempt_number"],
            ["Run ID", "Task ID", "Status", "Outcome", "Started", "Completed At", "Attempt"],
        )
    else:
        print_json(runs)


@app.command("get")
def get_run(
    run_id: str = typer.Argument(..., help="Run ID"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Get a specific run by ID."""
    db_client = _get_db_client()

    run = db_client.get_run(run_id)
    if not run:
        print_error(f"Run not found: {run_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [run],
            ["id", "task_id", "task_name", "status", "task_outcome", "started_at", "completed_at", "session_id", "exit_code"],
            ["Run ID", "Task ID", "Task Name", "Status", "Outcome", "Started", "Completed At", "Session ID", "Exit Code"],
        )
    else:
        print_json(run)


@app.command("retry")
def retry_run(
    run_id: str = typer.Argument(..., help="Run ID to retry"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Retry a failed run."""
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    # Get the run
    run = db_client.get_run(run_id)
    if not run:
        print_error(f"Run not found: {run_id}")
        raise typer.Exit(1)

    if run.status not in (RunStatus.FAILURE, RunStatus.TIMEOUT):
        print_error(f"Can only retry failed or timed-out runs. Current status: {run.status.value}")
        raise typer.Exit(1)

    # Get the task
    task = db_client.get_task(run.task_id)
    if not task:
        print_error(f"Task not found: {run.task_id}")
        raise typer.Exit(1)

    # Check retry limit
    if run.attempt_number >= task.max_retries:
        print_error(f"Max retry attempts ({task.max_retries}) reached")
        raise typer.Exit(1)

    # Execute a new run
    new_run = scheduler.run_job_now(run.task_id)
    if not new_run:
        print_error("Failed to retry run")
        raise typer.Exit(1)

    if table:
        print_table(
            [new_run],
            ["id", "task_id", "status", "started_at", "attempt_number"],
            ["Run ID", "Task ID", "Status", "Started", "Attempt"],
        )
    else:
        print_json(new_run)

    print_success(f"Run retried successfully. New run ID: {new_run.id}")
