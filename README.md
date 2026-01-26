# Claude Task Scheduler

A command-line tool for scheduling and executing Claude Code prompts with auto-resume, notifications, and logging.

## Features

- **Flexible Scheduling**: Schedule using friendly strings ("daily at 9AM", "every monday at 9AM") or cron expressions
- **Auto-Retry**: Automatic retry with exponential backoff on failure
- **Notifications**: Send notifications via Slack, email, and macOS desktop notifications on task events
- **Session Tracking**: Track Claude Code session IDs for debugging
- **Docker Ready**: Run as a daemon in a Docker container

## Installation

```bash
cd claude-task-scheduler
pip install -e .
```

After installation, the `claude-task-scheduler` command will be available.

## Quick Start

```bash
# Create a scheduled task
claude-task-scheduler tasks create \
  --name "Daily Report" \
  --prompt "Generate the daily sales report and save to /reports" \
  --project ~/projects/my-project \
  --schedule "daily at 9AM" \
  --model opus

# List all tasks
claude-task-scheduler tasks list --table

# Start the scheduler daemon
claude-task-scheduler daemon start
```

## Commands

### Tasks

Manage scheduled tasks (create, list, get, update, delete, enable, disable, trigger).

```bash
# Create a task with friendly schedule
claude-task-scheduler tasks create \
  --name "My Task" \
  --prompt "Your prompt here" \
  --project /path/to/project \
  --schedule "daily at 9AM" \
  --model opus \
  --max-retries 3 \
  --notification-channels slack,macos

# Create a task with cron expression
claude-task-scheduler tasks create \
  --name "Weekly Report" \
  --prompt "Generate weekly report" \
  --project /path/to/project \
  --schedule "0 9 * * 1" \
  --model opus

# List tasks
claude-task-scheduler tasks list
claude-task-scheduler tasks list --table
claude-task-scheduler tasks list --enabled

# Get task details
claude-task-scheduler tasks get TASK_ID

# Update a task schedule
claude-task-scheduler tasks update TASK_ID --name "New Name" --schedule "every monday at 10AM"

# Enable/disable a task
claude-task-scheduler tasks enable TASK_ID
claude-task-scheduler tasks disable TASK_ID

# Trigger a task to run immediately
claude-task-scheduler tasks trigger TASK_ID

# Delete a task
claude-task-scheduler tasks delete TASK_ID
claude-task-scheduler tasks delete TASK_ID --force
```

### Runs

View task execution history.

```bash
# List all runs
claude-task-scheduler runs list
claude-task-scheduler runs list --table

# Filter by task
claude-task-scheduler runs list --task-id TASK_ID

# Filter by status
claude-task-scheduler runs list --status failed

# Get run details
claude-task-scheduler runs get RUN_ID

# Retry a failed run
claude-task-scheduler runs retry RUN_ID
```

### Daemon

Control the scheduler daemon.

```bash
# Start the daemon (foreground)
claude-task-scheduler start

# Check health
claude-task-scheduler healthcheck
claude-task-scheduler healthcheck --table

# Stop the daemon
claude-task-scheduler stop
```

## Schedule Formats

The `--schedule` option accepts friendly human-readable formats or standard cron expressions.

### Friendly Formats

| Format | Cron Equivalent |
|--------|-----------------|
| `every minute` | `* * * * *` |
| `every 5 minutes` | `*/5 * * * *` |
| `every 30 minutes` | `*/30 * * * *` |
| `hourly` | `0 * * * *` |
| `every 2 hours` | `0 */2 * * *` |
| `daily at 9AM` | `0 9 * * *` |
| `every day at 12PM` | `0 12 * * *` |
| `every monday at 9AM` | `0 9 * * 1` |
| `every friday at 5PM` | `0 17 * * 5` |
| `every month on the 1st at 9AM` | `0 9 1 * *` |
| `monthly on the 15th at 12PM` | `0 12 15 * *` |

### Cron Expressions

Standard 5-field cron expressions are also supported:

| Expression | Description |
|------------|-------------|
| `0 9 * * *` | Every day at 9 AM |
| `0 9 * * 1-5` | Weekdays at 9 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 0 1 * *` | First of every month at midnight |
| `0 8,12,18 * * *` | At 8 AM, 12 PM, and 6 PM daily |

## Notifications

Tasks can send notifications via Slack, email, and macOS desktop notifications when:
- **start**: Task execution begins
- **success**: Task completes successfully
- **error**: Task fails

### Notification Channels

Channels are standalone entities that you create once and assign to tasks by ID.

```bash
# Create notification channels
claude-task-scheduler channels slack create --name "Dev Alerts" --default
claude-task-scheduler channels gmail create --email "admin@example.com" --default
claude-task-scheduler channels macos create --sound default --default

# List channels
claude-task-scheduler channels slack list --table
claude-task-scheduler channels gmail list --table
claude-task-scheduler channels macos list --table
```

### Assigning Channels to Tasks

Use `--notification-channels` (or `-N`) with a comma-separated list of channel types. Default channels for each type are automatically assigned:

```bash
# Use default channels for multiple types
claude-task-scheduler tasks create \
  --name "Important Task" \
  --prompt "..." \
  --project /path \
  --schedule "daily at 9AM" \
  --model opus \
  --notification-channels slack,gmail,macos

# Just Slack and macOS desktop notifications
claude-task-scheduler tasks create \
  --name "Another Task" \
  --prompt "..." \
  --project /path \
  --schedule "every monday at 9AM" \
  --model opus \
  -N slack,macos
```

**Valid channel types:** `slack`, `gmail`, `macos`

**Requirements:**
- `slack` - Slack notifications require the `slack` CLI to be installed and authenticated
- `gmail` - Email notifications require the `google` CLI to be installed and authenticated
- `macos` - Desktop notifications require the `notifier` CLI (terminal-notifier wrapper, macOS only)

## Docker Deployment

Build and run the scheduler as a Docker container:

```bash
# Build the image
docker-compose build

# Start the daemon
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Docker Volumes

| Volume | Purpose |
|--------|---------|
| `/data` | SQLite database (persistent) |
| `/home/scheduler/.claude` | Claude Code config (mount from host) |
| `/projects` | Project directories for task execution |

### Environment Variables

```bash
ANTHROPIC_API_KEY=<your-api-key>  # Required for Claude Code
CLAUDE_DEFAULT_MODEL=opus         # Optional default model
```

## Data Storage

Tasks and runs are stored in SQLite at `~/.claude-task-scheduler/scheduler.db`.

To view task run output, use the `claude-code-sessions` CLI with the session ID from the run record.

## Output Formats

All commands support two output formats:

- **JSON** (default): Machine-readable for scripting
- **Table** (`--table`): Human-readable format

```bash
# JSON output (default)
claude-task-scheduler tasks list

# Table output
claude-task-scheduler tasks list --table
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 130 | User interrupted (Ctrl+C) |

## Requirements

- Python 3.9+
- Claude Code CLI installed and authenticated
- For notifications: `slack`, `google`, and/or `notifier` (for macOS desktop) CLIs

## License

MIT
