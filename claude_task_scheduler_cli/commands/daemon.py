"""Daemon management commands."""

import os
import signal
import sys
import time
from pathlib import Path

import typer

from ..db_client import DatabaseClient
from ..health import check_daemon_health, get_pid_file_path
from ..models.task import DaemonStatus
from ..output import print_error, print_info, print_json, print_success, print_table
from ..scheduler import SchedulerService

app = typer.Typer(help="Manage scheduler daemon", no_args_is_help=True)

# Global scheduler instance for signal handling
_scheduler: SchedulerService | None = None


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
    # Clean up PID file
    pid_file = get_pid_file_path()
    if pid_file.exists():
        pid_file.unlink()
    sys.exit(0)


def _daemonize():
    """Fork process to run as daemon."""
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        print_error(f"Fork #1 failed: {e}")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        print_error(f"Fork #2 failed: {e}")
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    with open("/dev/null", "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    # Redirect stdout/stderr to log file
    log_dir = Path.home() / ".claude-task-scheduler"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "daemon.log"
    with open(log_file, "a") as log:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())


def _write_pid_file():
    """Write PID file for daemon management."""
    pid_file = get_pid_file_path()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))


@app.command("start")
def start_daemon(
    background: bool = typer.Option(False, "--background", "-b", help="Run in background as daemon"),
):
    """Start the scheduler daemon.

    By default runs in the foreground. Use --background to daemonize.
    """
    global _scheduler

    # Check if already running
    health = check_daemon_health()
    if health.get("running"):
        print_error(f"Daemon already running (PID: {health.get('pid')})")
        raise typer.Exit(1)

    if background:
        print_info("Starting scheduler daemon in background...")
        _daemonize()

    _scheduler = SchedulerService()

    # Set up signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Write PID file
    _write_pid_file()

    if not background:
        print_info("Starting scheduler daemon...")

    _scheduler.start()

    job_count = _scheduler.get_job_count()

    if background:
        # Already daemonized, just log
        print(f"Scheduler started with {job_count} job(s), PID: {os.getpid()}")
    else:
        print_success(f"Scheduler started with {job_count} scheduled job(s)")
        print_info("Press Ctrl+C to stop")

    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if not background:
            print_info("Stopping scheduler...")
        _scheduler.stop()
        # Clean up PID file
        pid_file = get_pid_file_path()
        if pid_file.exists():
            pid_file.unlink()
        if not background:
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


@app.command("healthcheck")
def healthcheck(
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Check if the scheduler daemon is running and healthy.

    Connects to the daemon's Unix socket to verify it's running.
    Returns exit code 0 if healthy, 1 if not running.
    """
    health = check_daemon_health()

    if table:
        print_table(
            [health],
            ["running", "uptime_seconds", "job_count", "pid", "reason"],
            ["Running", "Uptime (s)", "Jobs", "PID", "Reason"],
        )
    else:
        print_json(health)

    raise typer.Exit(code=0 if health.get("running") else 1)


@app.command("stop")
def stop_daemon():
    """Stop the scheduler daemon."""
    # Check if daemon is running
    health = check_daemon_health()
    if not health.get("running"):
        print_info("Daemon is not running")
        return

    pid = health.get("pid")
    if not pid:
        # Try reading from PID file
        pid_file = get_pid_file_path()
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
            except ValueError:
                print_error("Invalid PID file")
                raise typer.Exit(1)
        else:
            print_error("Cannot determine daemon PID")
            raise typer.Exit(1)

    # Send SIGTERM to gracefully stop
    try:
        os.kill(pid, signal.SIGTERM)
        print_info(f"Sent SIGTERM to daemon (PID: {pid})")

        # Wait for daemon to stop
        for _ in range(10):
            time.sleep(0.5)
            health = check_daemon_health()
            if not health.get("running"):
                print_success("Daemon stopped")
                return

        print_error("Daemon did not stop in time, sending SIGKILL")
        os.kill(pid, signal.SIGKILL)
        print_success("Daemon killed")
    except ProcessLookupError:
        print_info("Daemon process not found (already stopped)")
        # Clean up stale PID file
        pid_file = get_pid_file_path()
        if pid_file.exists():
            pid_file.unlink()
    except PermissionError:
        print_error(f"Permission denied stopping daemon (PID: {pid})")
