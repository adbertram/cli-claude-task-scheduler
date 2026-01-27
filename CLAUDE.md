# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install in development mode
pip install -e .

# Run the CLI
claude-task-scheduler --help
claude-task-scheduler tasks --help
claude-task-scheduler runs --help
claude-task-scheduler channels --help

# Daemon commands (at root level)
claude-task-scheduler start           # Start scheduler daemon
claude-task-scheduler stop            # Stop scheduler daemon
claude-task-scheduler status          # Check if daemon is running

# Docker deployment
docker-compose build
docker-compose up -d
```

## Architecture

### Layer Overview

```
main.py                    # Typer CLI app, registers command modules
├── commands/              # CLI command handlers (tasks, runs, daemon, channels)
├── models/
│   ├── base.py           # CLIModel base class (Pydantic)
│   ├── task.py           # Task, Run, NotificationConfig Pydantic models
│   ├── notification.py   # NotificationChannel hierarchy
│   └── db.py             # SQLAlchemy ORM models
├── db_client.py          # Database operations (CRUD for tasks, runs, channels)
├── scheduler.py          # APScheduler-based task execution engine
├── notifications.py      # NotificationService - sends via external CLIs
└── output.py             # JSON/table output formatting
```

### Key Patterns

**Two Model Layers**: Pydantic models in `models/task.py` and `models/notification.py` for API/CLI, SQLAlchemy models in `models/db.py` for persistence. `db_client.py` converts between them.

**Channel Architecture**: Notification channels (Slack, Gmail, macOS) are standalone entities stored in their own tables. Tasks reference channels via many-to-many junction tables (`task_slack_channels`, `task_gmail_channels`, `task_macos_channels`). Create channels first, then assign by type using `--notification-channels slack,gmail,macos` (uses default channels for each type).

**Notification Flow**: `NotificationService` in `notifications.py` sends notifications by invoking external CLIs:
- Slack: `slack messages send <target> <message>`
- Gmail: `google gmail send --to <email> --subject <subject> --body <body> --confirm`
- macOS: `notifier send --title <title> --message <message> [--sound <sound>] [--ignore-dnd]`

**Scheduler Execution**: `SchedulerService` uses APScheduler with SQLite job store. Tasks execute via `_invoke_claude()` which runs `claude --print --model <model> --output-format json` in the task's project directory.

### Database

SQLite at `~/.claude-task-scheduler/scheduler.db`. Tables:
- `scheduled_tasks` - Task definitions
- `task_runs` - Execution history
- `notification_configs` - Per-task notification event settings
- `slack_notification_channels` / `gmail_notification_channels` / `macos_notification_channels` - Standalone channels
- `task_slack_channels` / `task_gmail_channels` / `task_macos_channels` - Junction tables

### Adding a New Notification Channel Type

1. Add Pydantic model in `models/notification.py` extending `NotificationChannel`
2. Add SQLAlchemy model in `models/db.py` with many-to-many relationship to tasks
3. Add CRUD methods in `db_client.py`
4. Add `_send_<type>()` method in `notifications.py`
5. Update `_send()` to iterate over new channel type
6. Add CLI commands in `commands/notification_channels.py`
