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


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse time string like '12AM', '9PM', '14:30', '9:00AM' into (hour, minute).

    Returns (hour in 24h format, minute).
    """
    import re

    time_str = time_str.strip().upper()

    # Handle 24-hour format with minutes (e.g., "14:30")
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        raise ValueError(f"Invalid time: {time_str}")

    # Handle 12-hour format with minutes (e.g., "9:30AM", "12:00PM")
    match = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3)
        if hour < 1 or hour > 12 or minute > 59:
            raise ValueError(f"Invalid time: {time_str}")
        if period == "AM":
            hour = 0 if hour == 12 else hour
        else:  # PM
            hour = 12 if hour == 12 else hour + 12
        return hour, minute

    # Handle simple format (e.g., "9AM", "12PM", "12AM")
    match = re.match(r'^(\d{1,2})\s*(AM|PM)$', time_str)
    if match:
        hour = int(match.group(1))
        period = match.group(2)
        if hour < 1 or hour > 12:
            raise ValueError(f"Invalid time: {time_str}")
        if period == "AM":
            hour = 0 if hour == 12 else hour
        else:  # PM
            hour = 12 if hour == 12 else hour + 12
        return hour, 0

    raise ValueError(f"Cannot parse time: {time_str}")


def _parse_day_of_week(day_str: str) -> int:
    """Parse day of week string to cron number (0=Sunday)."""
    day_map = {
        "sunday": 0, "sun": 0,
        "monday": 1, "mon": 1,
        "tuesday": 2, "tue": 2, "tues": 2,
        "wednesday": 3, "wed": 3,
        "thursday": 4, "thu": 4, "thur": 4, "thurs": 4,
        "friday": 5, "fri": 5,
        "saturday": 6, "sat": 6,
    }
    day_lower = day_str.lower().strip()
    if day_lower in day_map:
        return day_map[day_lower]
    raise ValueError(f"Unknown day of week: {day_str}")


def _parse_schedule(schedule: str) -> Optional[str]:
    """Parse a friendly schedule string into a cron expression.

    Supported formats:
    - "every minute" → "* * * * *"
    - "every N minutes" → "*/N * * * *"
    - "every N hours" → "0 */N * * *"
    - "hourly" / "every hour" → "0 * * * *"
    - "daily at 9AM" / "every day at 9AM" → "0 9 * * *"
    - "every monday at 9AM" → "0 9 * * 1"
    - "every month on the 1st at 9AM" → "0 9 1 * *"
    - Raw cron expression (5 space-separated fields) → returned as-is

    Returns:
        Cron expression string, or None if parsing fails.
    """
    import re

    schedule = schedule.strip()

    # Check if it's already a cron expression (5 space-separated fields)
    if len(schedule.split()) == 5:
        return schedule

    schedule_lower = schedule.lower()

    # "every minute"
    if schedule_lower == "every minute":
        return "* * * * *"

    # "every N minutes" or "every N minute"
    match = re.match(r'^every\s+(\d+)\s+minutes?$', schedule_lower)
    if match:
        interval = int(match.group(1))
        if 1 <= interval <= 59:
            return f"*/{interval} * * * *"
        return None

    # "every N hours" or "every N hour"
    match = re.match(r'^every\s+(\d+)\s+hours?$', schedule_lower)
    if match:
        interval = int(match.group(1))
        if 1 <= interval <= 23:
            return f"0 */{interval} * * *"
        return None

    # "hourly" or "every hour"
    if schedule_lower in ("hourly", "every hour"):
        return "0 * * * *"

    # "daily at TIME" or "every day at TIME"
    match = re.match(r'^(?:daily|every\s+day)\s+(?:at\s+)?(.+)$', schedule_lower)
    if match:
        try:
            hour, minute = _parse_time(match.group(1))
            return f"{minute} {hour} * * *"
        except ValueError:
            return None

    # "every WEEKDAY at TIME" (e.g., "every monday at 9AM")
    match = re.match(r'^every\s+(\w+)\s+(?:at\s+)?(.+)$', schedule_lower)
    if match:
        day_str = match.group(1)
        time_str = match.group(2)
        try:
            day_num = _parse_day_of_week(day_str)
            hour, minute = _parse_time(time_str)
            return f"{minute} {hour} * * {day_num}"
        except ValueError:
            pass  # Not a valid day of week, continue

    # "every month on the Nth at TIME" or "monthly on the Nth at TIME"
    match = re.match(r'^(?:every\s+month|monthly)\s+(?:on\s+)?(?:the\s+)?(\d+)(?:st|nd|rd|th)?\s+(?:at\s+)?(.+)$', schedule_lower)
    if match:
        day_of_month = int(match.group(1))
        time_str = match.group(2)
        if 1 <= day_of_month <= 31:
            try:
                hour, minute = _parse_time(time_str)
                return f"{minute} {hour} {day_of_month} * *"
            except ValueError:
                return None

    # Not recognized as friendly format
    return None


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
    schedule: Optional[str] = typer.Option(
        None, "--schedule", "-s",
        help="Schedule: 'every 5 minutes', 'daily at 9AM', 'every monday at 9AM', or cron expression",
    ),
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

    Tasks can be created without a schedule and updated later with 'tasks update --schedule'.
    Tasks without a schedule can only be run manually via 'tasks trigger'.

    Use --notification-channels to specify which notification types to use.
    Default channels for each type will be automatically assigned.

    Schedule formats:
        - "every minute"
        - "every 5 minutes", "every 30 minutes"
        - "every 2 hours", "hourly"
        - "daily at 9AM", "every day at 12PM"
        - "every monday at 9AM", "every friday at 5PM"
        - "every month on the 1st at 9AM", "monthly on the 15th at 12PM"
        - Raw cron: "0 9 * * *", "*/15 * * * *"

    Examples:
        claude-task-scheduler tasks create -n "My Task" -p "Do something" -d /path -m opus
        claude-task-scheduler tasks create -n "Daily" -p "Do it" -d /path -m opus -s "daily at 9AM"
        claude-task-scheduler tasks create -n "Weekly" -p "Do it" -d /path -m opus -s "every monday at 9AM"
        --notification-channels slack,macos
    """
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    # Parse and validate schedule if provided
    cron_expression = None
    if schedule:
        cron_expression = _parse_schedule(schedule)
        if cron_expression is None:
            print_error(f"Invalid schedule: {schedule}")
            print_error("Use formats like: 'every 5 minutes', 'daily at 9AM', 'every monday at 9AM', or a cron expression")
            raise typer.Exit(1)
        if not scheduler.validate_cron(cron_expression):
            print_error(f"Invalid schedule expression: {schedule}")
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
        cron_expression=cron_expression,
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

    # Warn if no schedule set
    if not schedule:
        print_warning(
            "Task created without a schedule. It can only be run manually via:\n"
            "  claude-task-scheduler tasks trigger <task-id>\n"
            "To add a schedule: claude-task-scheduler tasks update <task-id> --schedule 'daily at 9AM'"
        )
    else:
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
        if task.enabled and task.cron_expression:
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
        task_dict["schedule_friendly"] = _cron_to_friendly(task.cron_expression) if task.cron_expression else "manual only"
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

    # Add next run time if task has a schedule
    if task.enabled and task.cron_expression:
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
    schedule: Optional[str] = typer.Option(
        None, "--schedule", "-s",
        help="Schedule: 'every 5 minutes', 'daily at 9AM', 'every monday at 9AM', or cron expression",
    ),
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

    Schedule formats:
        - "every minute"
        - "every 5 minutes", "every 30 minutes"
        - "every 2 hours", "hourly"
        - "daily at 9AM", "every day at 12PM"
        - "every monday at 9AM", "every friday at 5PM"
        - "every month on the 1st at 9AM", "monthly on the 15th at 12PM"
        - Raw cron: "0 9 * * *", "*/15 * * * *"

    Examples:
        --schedule "daily at 9AM"
        --schedule "every monday at 9AM"
        --notification-channels slack,macos
    """
    db_client = _get_db_client()
    scheduler = _get_scheduler()

    # Parse and validate schedule if provided
    cron_expression = None
    if schedule:
        cron_expression = _parse_schedule(schedule)
        if cron_expression is None:
            print_error(f"Invalid schedule: {schedule}")
            print_error("Use formats like: 'every 5 minutes', 'daily at 9AM', 'every monday at 9AM', or a cron expression")
            raise typer.Exit(1)
        if not scheduler.validate_cron(cron_expression):
            print_error(f"Invalid schedule expression: {schedule}")
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
        cron_expression=cron_expression,
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
