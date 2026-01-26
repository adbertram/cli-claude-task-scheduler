"""Daemon management commands."""

import signal
import sys
import time

import typer

from ..db_client import DatabaseClient
from ..models.task import DaemonStatus
from ..output import print_error, print_info, print_json, print_success, print_table
from ..scheduler import SchedulerService

app = typer.Typer(help="Manage scheduler daemon", no_args_is_help=True)

# Global scheduler instance for signal handling
_scheduler: SchedulerService | None = None


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _scheduler
    print_info("\nShutting down scheduler...")
    if _scheduler:
        _scheduler.stop()
    sys.exit(0)


@app.command("start")
def start_daemon():
    """Start the scheduler daemon.

    Runs in the foreground. Use Ctrl+C to stop.
    For background execution, use Docker or systemd.
    """
    global _scheduler

    _scheduler = SchedulerService()

    # Set up signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    print_info("Starting scheduler daemon...")
    _scheduler.start()

    job_count = _scheduler.get_job_count()
    print_success(f"Scheduler started with {job_count} scheduled job(s)")
    print_info("Press Ctrl+C to stop")

    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print_info("Stopping scheduler...")
        _scheduler.stop()
        print_success("Scheduler stopped")


@app.command("status")
def daemon_status(
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Check scheduler daemon status.

    Note: This only shows static information since the daemon
    runs in a separate process. For live status, check the
    daemon's output directly.
    """
    db_client = DatabaseClient()
    scheduler = SchedulerService()

    # Get task counts
    all_tasks = db_client.list_tasks()
    enabled_tasks = [t for t in all_tasks if t.enabled]

    # Build next runs list
    next_runs = []
    for task in enabled_tasks[:10]:
        next_run = scheduler.get_next_run_time(task.cron_expression)
        if next_run:
            next_runs.append({
                "task_id": task.id,
                "task_name": task.name,
                "next_run_at": next_run.isoformat(),
            })

    status = DaemonStatus(
        running=False,  # Can't detect from separate process
        job_count=len(enabled_tasks),
        uptime_seconds=None,
        next_runs=next_runs,
    )

    if table:
        # Print summary
        print_table(
            [{"total_tasks": len(all_tasks), "enabled_tasks": len(enabled_tasks)}],
            ["total_tasks", "enabled_tasks"],
            ["Total Tasks", "Enabled Tasks"],
        )
        # Print next runs
        if next_runs:
            print_info("\nNext scheduled runs:")
            print_table(
                next_runs,
                ["task_name", "next_run_at"],
                ["Task", "Next Run"],
            )
    else:
        print_json(status)

    print_info("\nNote: Run 'daemon start' to start the scheduler")


@app.command("stop")
def stop_daemon():
    """Stop the scheduler daemon.

    Note: This command is informational only. The daemon runs
    as a foreground process and should be stopped with Ctrl+C
    or by sending SIGTERM to the process.
    """
    print_info("The scheduler daemon runs in the foreground.")
    print_info("To stop it:")
    print_info("  - Press Ctrl+C in the terminal running 'daemon start'")
    print_info("  - Or send SIGTERM: kill <pid>")
    print_info("  - Or stop the Docker container")
