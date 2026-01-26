"""Notification channel models for scheduled tasks.

This module defines the notification channel hierarchy:
- NotificationChannel: Base class for all notification channels
- SlackNotificationChannel: Slack-specific channel with delivery options
- GmailNotificationChannel: Email-specific channel
- MacosNotificationChannel: macOS desktop notification channel
"""

from enum import Enum
from typing import Optional

from pydantic import Field

from .base import CLIModel


class NotificationChannel(CLIModel):
    """Base notification channel configuration.

    All notification channels share these common fields:
    - id: Unique identifier for the channel
    - channel_name: Human-readable name (e.g., "Dev Team Alerts")
    - enabled: Whether this channel is active
    - is_default: Whether this is a default channel auto-assigned to new tasks
    """

    id: str = Field(frozen=True)
    channel_name: str
    enabled: bool = True
    is_default: bool = False


class SlackDeliveryMethod(str, Enum):
    """Method for delivering Slack notifications."""

    CHANNEL = "channel"
    DIRECT_MESSAGE = "direct_message"


class SlackDeliveryTarget(CLIModel):
    """Defines how to deliver Slack notifications.

    Either channel_id or user_id should be set based on the method:
    - CHANNEL: Set channel_id to the Slack channel ID
    - DIRECT_MESSAGE: Set user_id to the Slack user ID
    """

    method: SlackDeliveryMethod = SlackDeliveryMethod.DIRECT_MESSAGE
    channel_id: Optional[str] = None
    user_id: Optional[str] = None


class SlackNotificationChannel(NotificationChannel):
    """Slack-specific notification channel.

    Supports sending to either a Slack channel or direct message.
    """

    workspace_id: Optional[str] = None
    delivery: SlackDeliveryTarget


class GmailNotificationChannel(NotificationChannel):
    """Gmail-specific notification channel.

    Sends email notifications to the specified address.
    """

    email_address: str


class MacosNotificationChannel(NotificationChannel):
    """macOS desktop notification channel.

    Sends desktop notifications via the notifier CLI (terminal-notifier wrapper).
    """

    sound: Optional[str] = None
    ignore_dnd: bool = False
