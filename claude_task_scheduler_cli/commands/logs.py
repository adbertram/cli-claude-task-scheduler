"""Task log management commands."""

from datetime import datetime, timedelta
from typing import Optional

import typer

from ..db_client import DatabaseClient
from ..models.log import LogEventType, LogLevel
from ..output import print_error, print_json, print_success, print_table

app = typer.Typer(help="View and manage task activity logs", no_args_is_help=True)


def _get_db_client() -> DatabaseClient:
    """Get database client."""
    return DatabaseClient()


def _parse_datetime(value: str) -> Optional[datetime]:
    """Parse a datetime string.

    Supports:
    - ISO format: 2024-01-15T10:30:00
    - Date only: 2024-01-15
    - Relative: -1h, -2d, -1w (hours, days, weeks ago)
    """
    if not value:
        return None

    # Relative time parsing
    if value.startswith("-"):
        try:
            amount = int(value[1:-1])
            unit = value[-1].lower()
            now = datetime.utcnow()
            if unit == "h":
                return now - timedelta(hours=amount)
            elif unit == "d":
                return now - timedelta(days=amount)
            elif unit == "w":
                return now - timedelta(weeks=amount)
        except (ValueError, IndexError):
            pass

    # ISO format parsing
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass

    # Date only parsing
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        pass

    return None


@app.command("list")
def list_logs(
    task_id: Optional[str] = typer.Option(None, "--task-id", "-t", help="Filter by task ID"),
    run_id: Optional[str] = typer.Option(None, "--run-id", "-r", help="Filter by run ID"),
    event_type: Optional[str] = typer.Option(
        None, "--event-type", "-e",
        help="Filter by event type (task_start, task_complete, task_failed, task_retry, command_executed, output_captured)"
    ),
    level: Optional[str] = typer.Option(
        None, "--level", "-l",
        help="Filter by minimum log level (debug, info, warning, error)"
    ),
    since: Optional[str] = typer.Option(
        None, "--since", "-s",
        help="Filter logs after this time (ISO format or relative: -1h, -2d, -1w)"
    ),
    until: Optional[str] = typer.Option(
        None, "--until", "-u",
        help="Filter logs before this time (ISO format or relative)"
    ),
    limit: int = typer.Option(100, "--limit", help="Maximum number of results"),
    offset: int = typer.Option(0, "--offset", help="Number of results to skip"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """List task activity logs."""
    db_client = _get_db_client()

    # Parse event type filter
    event_type_filter = None
    if event_type:
        try:
            event_type_filter = LogEventType(event_type.lower())
        except ValueError:
            valid_types = ", ".join([e.value for e in LogEventType])
            print_error(f"Invalid event type: {event_type}. Valid values: {valid_types}")
            raise typer.Exit(1)

    # Parse level filter
    level_filter = None
    if level:
        try:
            level_filter = LogLevel(level.lower())
        except ValueError:
            valid_levels = ", ".join([l.value for l in LogLevel])
            print_error(f"Invalid level: {level}. Valid values: {valid_levels}")
            raise typer.Exit(1)

    # Parse datetime filters
    since_dt = _parse_datetime(since) if since else None
    until_dt = _parse_datetime(until) if until else None

    if since and not since_dt:
        print_error(f"Invalid datetime format: {since}")
        raise typer.Exit(1)
    if until and not until_dt:
        print_error(f"Invalid datetime format: {until}")
        raise typer.Exit(1)

    logs = db_client.list_logs(
        task_id=task_id,
        run_id=run_id,
        event_type=event_type_filter,
        level=level_filter,
        since=since_dt,
        until=until_dt,
        limit=limit,
        offset=offset,
    )

    if table:
        print_table(
            logs,
            ["id", "task_id", "event_type", "level", "message", "created_at"],
            ["Log ID", "Task ID", "Event Type", "Level", "Message", "Created At"],
        )
    else:
        print_json(logs)


@app.command("get")
def get_log(
    log_id: str = typer.Argument(..., help="Log ID"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Get a specific log entry by ID."""
    db_client = _get_db_client()

    log = db_client.get_log(log_id)
    if not log:
        print_error(f"Log not found: {log_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [log],
            ["id", "task_id", "task_name", "run_id", "run_attempt", "event_type", "level", "message", "created_at"],
            ["Log ID", "Task ID", "Task Name", "Run ID", "Attempt", "Event Type", "Level", "Message", "Created At"],
        )
    else:
        print_json(log)


@app.command("tail")
def tail_logs(
    n: int = typer.Option(20, "-n", "--lines", help="Number of recent logs to show"),
    task_id: Optional[str] = typer.Option(None, "--task-id", "-t", help="Filter by task ID"),
    run_id: Optional[str] = typer.Option(None, "--run-id", "-r", help="Filter by run ID"),
    level: Optional[str] = typer.Option(
        None, "--level", "-l",
        help="Filter by minimum log level (debug, info, warning, error)"
    ),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Show the most recent log entries (like tail -n)."""
    db_client = _get_db_client()

    # Parse level filter
    level_filter = None
    if level:
        try:
            level_filter = LogLevel(level.lower())
        except ValueError:
            valid_levels = ", ".join([l.value for l in LogLevel])
            print_error(f"Invalid level: {level}. Valid values: {valid_levels}")
            raise typer.Exit(1)

    logs = db_client.list_logs(
        task_id=task_id,
        run_id=run_id,
        level=level_filter,
        limit=n,
    )

    if table:
        print_table(
            logs,
            ["id", "task_id", "event_type", "level", "message", "created_at"],
            ["Log ID", "Task ID", "Event Type", "Level", "Message", "Created At"],
        )
    else:
        print_json(logs)


@app.command("delete")
def delete_logs(
    task_id: Optional[str] = typer.Option(None, "--task-id", "-t", help="Delete logs for this task only"),
    before: Optional[str] = typer.Option(
        None, "--before", "-b",
        help="Delete logs created before this time (ISO format or relative: -1d, -1w)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete log entries matching the criteria."""
    db_client = _get_db_client()

    # Parse datetime filter
    before_dt = _parse_datetime(before) if before else None
    if before and not before_dt:
        print_error(f"Invalid datetime format: {before}")
        raise typer.Exit(1)

    # Require at least one filter
    if not task_id and not before_dt:
        print_error("At least one filter (--task-id or --before) is required")
        raise typer.Exit(1)

    # Count logs to be deleted
    count = db_client.count_logs(task_id=task_id)
    if before_dt:
        # Get more accurate count with before filter
        logs = db_client.list_logs(task_id=task_id, until=before_dt, limit=100000)
        count = len(logs)

    if count == 0:
        print_error("No logs found matching the criteria")
        raise typer.Exit(1)

    # Confirm deletion
    if not force:
        confirm_msg = f"Delete {count} log(s)?"
        if task_id:
            confirm_msg = f"Delete {count} log(s) for task {task_id}?"
        if before_dt:
            confirm_msg = f"Delete {count} log(s) created before {before_dt.isoformat()}?"

        if not typer.confirm(confirm_msg):
            print_error("Aborted")
            raise typer.Exit(1)

    deleted = db_client.delete_logs(task_id=task_id, before=before_dt)
    print_success(f"Deleted {deleted} log(s)")


@app.command("stats")
def log_stats(
    task_id: Optional[str] = typer.Option(None, "--task-id", "-t", help="Show stats for this task only"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Show log statistics."""
    db_client = _get_db_client()

    # Count by event type
    event_counts = {}
    for event_type in LogEventType:
        logs = db_client.list_logs(
            task_id=task_id,
            event_type=event_type,
            limit=100000,
        )
        event_counts[event_type.value] = len(logs)

    # Count by level
    level_counts = {}
    for level in LogLevel:
        logs = db_client.list_logs(
            task_id=task_id,
            level=level,
            limit=100000,
        )
        # This counts level and above, so we need to count exact matches
        level_counts[level.value] = len([l for l in logs if l.level == level])

    # Total count
    total_count = db_client.count_logs(task_id=task_id)

    # Recent activity (last 24h)
    since_24h = datetime.utcnow() - timedelta(hours=24)
    recent_logs = db_client.list_logs(task_id=task_id, since=since_24h, limit=100000)
    recent_count = len(recent_logs)

    stats = {
        "total_logs": total_count,
        "logs_last_24h": recent_count,
        "by_event_type": event_counts,
        "by_level": level_counts,
    }

    if task_id:
        stats["task_id"] = task_id

    if table:
        # Format for table display
        rows = [
            {"metric": "Total Logs", "value": total_count},
            {"metric": "Logs (Last 24h)", "value": recent_count},
        ]
        for event_type, count in event_counts.items():
            rows.append({"metric": f"Event: {event_type}", "value": count})
        for level, count in level_counts.items():
            rows.append({"metric": f"Level: {level}", "value": count})

        print_table(rows, ["metric", "value"], ["Metric", "Count"])
    else:
        print_json(stats)
