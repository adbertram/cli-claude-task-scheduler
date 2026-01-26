"""Task management commands."""

from typing import Optional

import typer

from ..db_client import DatabaseClient
from ..health import check_daemon_health
from ..models.task import (
    NotificationEvent,
    ScheduledTaskCreate,
    ScheduledTaskUpdate,
)
from ..output import print_error, print_json, print_success, print_table, print_warning
from ..scheduler import SchedulerService

app = typer.Typer(help="Manage scheduled tasks", no_args_is_help=True)

VALID_CHANNEL_TYPES = {"slack", "gmail", "macos"}


def _format_hour(hour: int) -> str:
    """Format hour as 12-hour time with AM/PM."""
    if hour == 0:
        return "12AM"
    elif hour < 12:
        return f"{hour}AM"
    elif hour == 12:
        return "12PM"
    else:
        return f"{hour - 12}PM"


def _cron_to_friendly(cron: str) -> str:
    """Convert cron expression to human-readable format."""
    parts = cron.split()
    if len(parts) != 5:
        return cron

    minute, hour, dom, month, dow = parts

    # Every minute
    if cron == "* * * * *":
        return "every minute"

    # Every N minutes
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
        interval = minute[2:]
        return f"every {interval} min"

    # Hourly at specific minute
    if minute.isdigit() and hour == "*" and dom == "*" and month == "*" and dow == "*":
        m = int(minute)
        if m == 0:
            return "hourly"
        return f"hourly @:{minute.zfill(2)}"

    # Daily at specific time
    if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow == "*":
        return f"daily @{_format_hour(int(hour))}"

    # Weekly (specific day of week)
    if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow.isdigit():
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        day_idx = int(dow)
        if 0 <= day_idx <= 6:
            return f"{days[day_idx]} @{_format_hour(int(hour))}"

    # Monthly (specific day of month)
    if minute.isdigit() and hour.isdigit() and dom.isdigit() and month == "*" and dow == "*":
        d = int(dom)
        suffix = "th"
        if d == 1 or d == 21 or d == 31:
            suffix = "st"
        elif d == 2 or d == 22:
            suffix = "nd"
        elif d == 3 or d == 23:
            suffix = "rd"
        return f"monthly {d}{suffix} @{_format_hour(int(hour))}"

    # Fallback to original cron
    return cron


def _get_db_client() -> DatabaseClient:
    """Get database client."""
    return DatabaseClient()


def _get_scheduler() -> SchedulerService:
    """Get scheduler service."""
    return SchedulerService()


def _parse_notification_channels(
    channels: Optional[str], db_client: "DatabaseClient"
) -> tuple[list[str], list[str], list[str]]:
    """Parse notification channel types and return default channel IDs for each type.

    Args:
        channels: Comma-separated channel types (slack, gmail, macos)
        db_client: Database client for fetching default channels

    Returns:
        Tuple of (slack_channel_ids, gmail_channel_ids, macos_channel_ids)
    """
    slack_ids = []
    gmail_ids = []
    macos_ids = []

    if not channels:
        return slack_ids, gmail_ids, macos_ids

    for channel_type in channels.split(","):
        channel_type = channel_type.strip().lower()
        if not channel_type:
            continue

        if channel_type not in VALID_CHANNEL_TYPES:
            print_error(f"Invalid channel type: {channel_type}. Valid types: {', '.join(sorted(VALID_CHANNEL_TYPES))}")
            raise typer.Exit(1)

        if channel_type == "slack":
            defaults = db_client.get_default_slack_channels()
            slack_ids.extend([ch.id for ch in defaults])
        elif channel_type == "gmail":
            defaults = db_client.get_default_gmail_channels()
            gmail_ids.extend([ch.id for ch in defaults])
        elif channel_type == "macos":
            defaults = db_client.get_default_macos_channels()
            macos_ids.extend([ch.id for ch in defaults])

    return slack_ids, gmail_ids, macos_ids


@app.command("create")
def create_task(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Claude Code prompt to execute"),
    project: str = typer.Option(..., "--project", "-d", help="Project directory path"),
    cron: str = typer.Option(..., "--cron", "-c", help="Cron expression (e.g., '0 9 * * *')"),
    model: str = typer.Option(..., "--model", "-m", help="Claude model (e.g., 'opus', 'sonnet')"),
    max_retries: int = typer.Option(3, "--max-retries", "-r", help="Maximum retry attempts"),
    timeout: int = typer.Option(3600, "--timeout", "-T", help="Execution timeout in seconds (60-86400)"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable task immediately"),
    notification_channels: Optional[str] = typer.Option(
        None,
        "--notification-channels", "-N",
        help="Channel types: slack, gmail, macos (comma-separated, uses default channels)",
    ),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Create a new scheduled task.

    Use --notification-channels to specify which notification types to use.
    Default channels for each type will be automatically assigned.

    Examples:
        --notification-channels slack,macos
        --notification-channels gmail
        --notification-channels slack,gmail,macos
    """
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    # Validate cron expression
    if not scheduler.validate_cron(cron):
        print_error(f"Invalid cron expression: {cron}")
        raise typer.Exit(1)

    # Validate timeout range
    if timeout < 60 or timeout > 86400:
        print_error("Timeout must be between 60 and 86400 seconds")
        raise typer.Exit(1)

    # Parse channel types and get default channel IDs
    slack_channel_ids, gmail_channel_ids, macos_channel_ids = _parse_notification_channels(
        notification_channels, db_client
    )

    # Create task
    task_data = ScheduledTaskCreate(
        name=name,
        prompt=prompt,
        project_path=project,
        cron_expression=cron,
        model=model,
        max_retries=max_retries,
        timeout_seconds=timeout,
        enabled=enabled,
        slack_channel_ids=slack_channel_ids,
        gmail_channel_ids=gmail_channel_ids,
        macos_channel_ids=macos_channel_ids,
    )

    task = db_client.create_task(task_data)

    if table:
        print_table(
            [task],
            ["id", "name", "cron_expression", "model", "enabled"],
            ["ID", "Name", "Schedule", "Model", "Enabled"],
        )
    else:
        print_json(task)

    print_success(f"Task '{name}' created successfully")

    # Check daemon health and warn if not running
    health = check_daemon_health()
    if not health.get("running"):
        print_warning(
            "Daemon is not running. Task will not execute until daemon is started.\n"
            "Run: claude-task-scheduler daemon start"
        )


@app.command("list")
def list_tasks(
    enabled_only: bool = typer.Option(False, "--enabled", "-e", help="Show only enabled tasks"),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum number of results"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
    filter: Optional[list[str]] = typer.Option(None, "--filter", "-f", help="Filter: field:op:value"),
    properties: Optional[str] = typer.Option(None, "--properties", "-p", help="Comma-separated list of fields"),
):
    """List all scheduled tasks."""
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    tasks = db_client.list_tasks(enabled_only=enabled_only, limit=limit)

    # Build output with notification channels summary
    output = []
    for task in tasks:
        if task.enabled:
            next_run = scheduler.get_next_run_time(task.cron_expression)
            task.next_run_at = next_run

        # Build notification channels summary
        channels = []
        if task.notification_config:
            if task.notification_config.slack_channels:
                channels.append("slack")
            if task.notification_config.gmail_channels:
                channels.append("gmail")
            if task.notification_config.macos_channels:
                channels.append("macos")

        task_dict = task.model_dump()
        task_dict["notification_channels"] = ", ".join(channels) if channels else "none"
        task_dict["schedule_friendly"] = _cron_to_friendly(task.cron_expression)
        task_dict["total_runs"] = db_client.count_runs(task.id)
        output.append(task_dict)

    if table:
        print_table(
            output,
            ["id", "name", "schedule_friendly", "model", "enabled", "notification_channels", "total_runs"],
            ["ID", "Name", "Schedule", "Model", "Enabled", "Notifications", "Runs"],
        )
    else:
        print_json(output)


@app.command("get")
def get_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Get a specific task by ID."""
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    task = db_client.get_task(task_id)
    if not task:
        print_error(f"Task not found: {task_id}")
        raise typer.Exit(1)

    # Add next run time
    if task.enabled:
        task.next_run_at = scheduler.get_next_run_time(task.cron_expression)

    if table:
        print_table(
            [task],
            ["id", "name", "prompt", "project_path", "cron_expression", "model", "enabled"],
            ["ID", "Name", "Prompt", "Project", "Schedule", "Model", "Enabled"],
        )
    else:
        print_json(task)


@app.command("update")
def update_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Task name"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Claude Code prompt"),
    project: Optional[str] = typer.Option(None, "--project", "-d", help="Project directory path"),
    cron: Optional[str] = typer.Option(None, "--cron", "-c", help="Cron expression"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Claude model"),
    max_retries: Optional[int] = typer.Option(None, "--max-retries", "-r", help="Maximum retry attempts"),
    timeout: Optional[int] = typer.Option(None, "--timeout", "-T", help="Execution timeout in seconds (60-86400)"),
    notification_channels: Optional[str] = typer.Option(
        None,
        "--notification-channels", "-N",
        help="Channel types: slack, gmail, macos (comma-separated, replaces existing)",
    ),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Update a scheduled task.

    Use --notification-channels to specify which notification types to use.
    Default channels for each type will be automatically assigned.
    This replaces any existing notification channel assignments.

    Examples:
        --notification-channels slack,macos
        --notification-channels gmail
        --notification-channels slack,gmail,macos
    """
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    # Validate cron if provided
    if cron and not scheduler.validate_cron(cron):
        print_error(f"Invalid cron expression: {cron}")
        raise typer.Exit(1)

    # Validate timeout if provided
    if timeout is not None and (timeout < 60 or timeout > 86400):
        print_error("Timeout must be between 60 and 86400 seconds")
        raise typer.Exit(1)

    # Parse channel types if provided
    slack_channel_ids = None
    gmail_channel_ids = None
    macos_channel_ids = None

    if notification_channels is not None:
        slack_channel_ids, gmail_channel_ids, macos_channel_ids = _parse_notification_channels(
            notification_channels, db_client
        )

    update_data = ScheduledTaskUpdate(
        name=name,
        prompt=prompt,
        project_path=project,
        cron_expression=cron,
        model=model,
        max_retries=max_retries,
        timeout_seconds=timeout,
        slack_channel_ids=slack_channel_ids,
        gmail_channel_ids=gmail_channel_ids,
        macos_channel_ids=macos_channel_ids,
    )

    task = db_client.update_task(task_id, update_data)
    if not task:
        print_error(f"Task not found: {task_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [task],
            ["id", "name", "cron_expression", "model", "enabled"],
            ["ID", "Name", "Schedule", "Model", "Enabled"],
        )
    else:
        print_json(task)

    print_success(f"Task '{task.name}' updated successfully")


@app.command("delete")
def delete_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    force: bool = typer.Option(False, "--force", "-F", help="Skip confirmation"),
):
    """Delete a scheduled task."""
    db_client = _get_db_client()

    task = db_client.get_task(task_id)
    if not task:
        print_error(f"Task not found: {task_id}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete task '{task.name}'?")
        if not confirm:
            raise typer.Abort()

    db_client.delete_task(task_id)
    print_success(f"Task '{task.name}' deleted successfully")


@app.command("enable")
def enable_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Enable a scheduled task."""
    db_client = _get_db_client()

    task = db_client.enable_task(task_id)
    if not task:
        print_error(f"Task not found: {task_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [task],
            ["id", "name", "enabled"],
            ["ID", "Name", "Enabled"],
        )
    else:
        print_json(task)

    print_success(f"Task '{task.name}' enabled")


@app.command("disable")
def disable_task(
    task_id: str = typer.Argument(..., help="Task ID"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Disable a scheduled task."""
    db_client = _get_db_client()

    task = db_client.disable_task(task_id)
    if not task:
        print_error(f"Task not found: {task_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [task],
            ["id", "name", "enabled"],
            ["ID", "Name", "Enabled"],
        )
    else:
        print_json(task)

    print_success(f"Task '{task.name}' disabled")


@app.command("trigger")
def trigger_task(
    task_id: str = typer.Argument(..., help="Task ID to trigger"),
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Trigger a task to run immediately."""
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    task = db_client.get_task(task_id)
    if not task:
        print_error(f"Task not found: {task_id}")
        raise typer.Exit(1)

    # Execute the task
    run = scheduler.run_job_now(task_id)
    if not run:
        print_error("Failed to trigger task")
        raise typer.Exit(1)

    if table:
        print_table(
            [run],
            ["id", "task_id", "status", "started_at", "session_id"],
            ["Run ID", "Task ID", "Status", "Started", "Session ID"],
        )
    else:
        print_json(run)

    print_success(f"Task '{task.name}' triggered successfully")
