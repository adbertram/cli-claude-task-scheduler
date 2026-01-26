"""Pydantic models for scheduled tasks and runs."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from .base import CLIModel
from .notification import (
    GmailNotificationChannel,
    MacosNotificationChannel,
    SlackNotificationChannel,
)


class TaskStatus(str, Enum):
    """Status of a task run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class NotificationEvent(str, Enum):
    """Events that trigger notifications."""

    START = "start"
    SUCCESS = "success"
    ERROR = "error"


class NotificationConfig(CLIModel):
    """Configuration for task notifications.

    Uses channel-based configuration for flexibility:
    - Multiple channels of the same type
    - Per-channel enable/disable
    - Slack DM vs channel delivery options
    - Desktop notifications via notifier CLI (macos)
    """

    id: str = Field(frozen=True)
    task_id: str = Field(frozen=True)
    events: list[NotificationEvent] = Field(
        default=[NotificationEvent.START, NotificationEvent.SUCCESS, NotificationEvent.ERROR]
    )
    slack_channels: list[SlackNotificationChannel] = Field(default_factory=list)
    gmail_channels: list[GmailNotificationChannel] = Field(default_factory=list)
    macos_channels: list[MacosNotificationChannel] = Field(default_factory=list)


class ScheduledTask(CLIModel):
    """A scheduled Claude Code task."""

    id: str = Field(frozen=True)
    name: str
    prompt: str
    project_path: str
    cron_expression: str
    model: str
    max_retries: int = 3
    timeout_seconds: int = 3600
    enabled: bool = True
    created_at: datetime = Field(frozen=True)
    updated_at: datetime = Field(frozen=True)
    next_run_at: Optional[datetime] = None


class ScheduledTaskDetail(ScheduledTask):
    """Scheduled task with notification config."""

    notification_config: Optional[NotificationConfig] = None


class SlackChannelCreate(CLIModel):
    """Model for creating a Slack notification channel.

    All fields are optional - database defaults will be used:
    - channel_name: "Slack DM"
    - workspace_id: "T0F2BD3QA" (ATA Learning)
    - delivery_method: "direct_message"
    - delivery_user_id: "U01RZG11N9K" (adbertram)
    """

    channel_name: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    workspace_id: Optional[str] = None
    delivery_method: Optional[str] = None
    delivery_channel_id: Optional[str] = None
    delivery_user_id: Optional[str] = None


class GmailChannelCreate(CLIModel):
    """Model for creating a Gmail notification channel.

    All fields are optional - database defaults will be used:
    - channel_name: "Email"
    - email_address: "adbertram@gmail.com"
    """

    channel_name: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    email_address: Optional[str] = None


class MacosChannelCreate(CLIModel):
    """Model for creating a macOS desktop notification channel.

    All fields are optional - database defaults will be used:
    - channel_name: "Desktop"
    - sound: None (no sound)
    - ignore_dnd: False
    """

    channel_name: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    sound: Optional[str] = None
    ignore_dnd: Optional[bool] = None


class ScheduledTaskCreate(CLIModel):
    """Model for creating a scheduled task.

    Channels are standalone entities that are assigned by ID.
    Create channels first via 'channels slack create', 'channels gmail create',
    or 'channels macos create', then assign them to tasks by ID.
    """

    name: str
    prompt: str
    project_path: str
    cron_expression: str
    model: str
    max_retries: int = 3
    timeout_seconds: int = 3600
    enabled: bool = True
    notification_events: list[NotificationEvent] = Field(
        default=[NotificationEvent.START, NotificationEvent.SUCCESS, NotificationEvent.ERROR]
    )
    slack_channel_ids: list[str] = Field(default_factory=list)
    gmail_channel_ids: list[str] = Field(default_factory=list)
    macos_channel_ids: list[str] = Field(default_factory=list)


class ScheduledTaskUpdate(CLIModel):
    """Model for updating a scheduled task.

    Channels are standalone entities that are assigned by ID.
    Use 'channels slack create', 'channels gmail create', or 'channels macos create'
    to create channels, then assign them here by ID.
    """

    name: Optional[str] = None
    prompt: Optional[str] = None
    project_path: Optional[str] = None
    cron_expression: Optional[str] = None
    model: Optional[str] = None
    max_retries: Optional[int] = None
    timeout_seconds: Optional[int] = None
    enabled: Optional[bool] = None
    notification_events: Optional[list[NotificationEvent]] = None
    slack_channel_ids: Optional[list[str]] = None
    gmail_channel_ids: Optional[list[str]] = None
    macos_channel_ids: Optional[list[str]] = None


class TaskRun(CLIModel):
    """A single execution of a scheduled task."""

    id: str = Field(frozen=True)
    task_id: str = Field(frozen=True)
    status: TaskStatus
    started_at: datetime = Field(frozen=True)
    completed_at: Optional[datetime] = None
    session_id: Optional[str] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    summary: Optional[str] = None
    attempt_number: int = 1


class TaskRunDetail(TaskRun):
    """Task run with task information."""

    task_name: Optional[str] = None


class DaemonStatus(CLIModel):
    """Status of the scheduler daemon."""

    running: bool
    job_count: int
    uptime_seconds: Optional[float] = None
    next_runs: list[dict] = Field(default_factory=list)
