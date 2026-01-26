"""Claude Task Scheduler CLI models.

All entities are defined here as Pydantic models for consistent
typing, validation, and JSON serialization.

Model Architecture:
- CLIModel: Base class with CLI-friendly configuration
- ScheduledTask: Scheduled Claude Code task
- TaskRun: Single execution of a scheduled task
- NotificationConfig: Notification settings per task
- NotificationChannel: Base class for notification channels
- SlackNotificationChannel: Slack-specific channel
- GmailNotificationChannel: Email-specific channel
- MacosNotificationChannel: macOS desktop notification channel
- DaemonStatus: Scheduler daemon status

Database Models:
- db.py contains SQLAlchemy models for persistence
"""

from .base import CLIModel
from .notification import (
    GmailNotificationChannel,
    MacosNotificationChannel,
    NotificationChannel,
    SlackDeliveryMethod,
    SlackDeliveryTarget,
    SlackNotificationChannel,
)
from .task import (
    DaemonStatus,
    GmailChannelCreate,
    MacosChannelCreate,
    NotificationConfig,
    NotifyOn,
    ScheduledTask,
    ScheduledTaskCreate,
    ScheduledTaskDetail,
    ScheduledTaskUpdate,
    SlackChannelCreate,
    TaskRun,
    TaskRunDetail,
    TaskStatus,
)

__all__ = [
    # Base
    "CLIModel",
    # Task models
    "ScheduledTask",
    "ScheduledTaskCreate",
    "ScheduledTaskDetail",
    "ScheduledTaskUpdate",
    # Run models
    "TaskRun",
    "TaskRunDetail",
    "TaskStatus",
    # Notification models
    "NotificationConfig",
    "NotifyOn",
    # Notification channel models
    "NotificationChannel",
    "SlackNotificationChannel",
    "SlackDeliveryMethod",
    "SlackDeliveryTarget",
    "GmailNotificationChannel",
    "MacosNotificationChannel",
    "SlackChannelCreate",
    "GmailChannelCreate",
    "MacosChannelCreate",
    # Daemon
    "DaemonStatus",
]
