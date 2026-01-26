"""Notification service for task execution events."""

import subprocess
import sys
from typing import Optional

from .db_client import DatabaseClient
from .models.notification import (
    GmailNotificationChannel,
    MacosNotificationChannel,
    SlackDeliveryMethod,
    SlackNotificationChannel,
)
from .models.task import (
    NotificationConfig,
    NotificationEvent,
    ScheduledTask,
    ScheduledTaskDetail,
    TaskRun,
)


class NotificationService:
    """Service for sending notifications via Slack, email, and desktop notifications."""

    def __init__(self, db_client: DatabaseClient):
        """Initialize the notification service.

        Args:
            db_client: Database client for fetching notification configs
        """
        self.db_client = db_client

    def notify_start(self, task: ScheduledTask | ScheduledTaskDetail, run: TaskRun) -> None:
        """Send notification when task starts.

        Args:
            task: The scheduled task
            run: The task run record
        """
        config = self._get_config(task)
        if not config or NotificationEvent.RUNNING not in config.events:
            return

        message = self._format_start_message(task, run)
        self._send(config, f"Task Started: {task.name}", message)

    def notify_success(self, task: ScheduledTask | ScheduledTaskDetail, run: TaskRun) -> None:
        """Send notification when task completes successfully.

        Args:
            task: The scheduled task
            run: The task run record
        """
        config = self._get_config(task)
        if not config or NotificationEvent.SUCCESS not in config.events:
            return

        message = self._format_success_message(task, run)
        self._send(config, f"Task Completed: {task.name}", message)

    def notify_error(self, task: ScheduledTask | ScheduledTaskDetail, run: TaskRun) -> None:
        """Send notification when task fails.

        Args:
            task: The scheduled task
            run: The task run record
        """
        config = self._get_config(task)
        if not config or NotificationEvent.FAILURE not in config.events:
            return

        message = self._format_error_message(task, run)
        self._send(config, f"Task Failed: {task.name}", message)

    def _get_config(self, task: ScheduledTask | ScheduledTaskDetail) -> Optional[NotificationConfig]:
        """Get notification config for a task."""
        if isinstance(task, ScheduledTaskDetail) and task.notification_config:
            return task.notification_config
        return self.db_client.get_notification_config(task.id)

    def _format_start_message(self, task: ScheduledTask, run: TaskRun) -> str:
        """Format start notification message."""
        return (
            f"Task: {task.name}\n"
            f"Status: Started\n"
            f"Run ID: {run.id}\n"
            f"Project: {task.project_path}\n"
            f"Model: {task.model}\n"
            f"Attempt: {run.attempt_number}"
        )

    def _format_success_message(self, task: ScheduledTask, run: TaskRun) -> str:
        """Format success notification message."""
        summary = run.summary or "Completed successfully"
        return (
            f"Task: {task.name}\n"
            f"Status: Completed\n"
            f"Run ID: {run.id}\n"
            f"Session ID: {run.session_id or 'N/A'}\n"
            f"Summary: {summary}"
        )

    def _format_error_message(self, task: ScheduledTask, run: TaskRun) -> str:
        """Format error notification message."""
        error = run.error_message or "Unknown error"
        return (
            f"Task: {task.name}\n"
            f"Status: Failed\n"
            f"Run ID: {run.id}\n"
            f"Attempt: {run.attempt_number}/{task.max_retries}\n"
            f"Error: {error}"
        )

    def _send(self, config: NotificationConfig, subject: str, message: str) -> None:
        """Send notification via configured channels.

        Args:
            config: Notification configuration
            subject: Message subject (for email/desktop title)
            message: Message body
        """
        for slack_channel in config.slack_channels:
            if slack_channel.enabled:
                self._send_slack(slack_channel, f"*{subject}*\n{message}")

        for gmail_channel in config.gmail_channels:
            if gmail_channel.enabled:
                self._send_email(gmail_channel.email_address, subject, message)

        for macos_channel in config.macos_channels:
            if macos_channel.enabled:
                self._send_macos(macos_channel, subject, message)

    def _send_slack(self, channel: SlackNotificationChannel, message: str) -> bool:
        """Send message via Slack notification channel.

        Args:
            channel: Slack notification channel configuration
            message: Message text

        Returns:
            True if sent successfully
        """
        try:
            # Determine target based on delivery method
            if channel.delivery.method == SlackDeliveryMethod.CHANNEL:
                target = channel.delivery.channel_id
            else:  # DIRECT_MESSAGE
                target = channel.delivery.user_id

            if not target:
                print(f"Slack channel '{channel.channel_name}' has no delivery target configured", file=sys.stderr)
                return False

            result = subprocess.run(
                ["slack", "messages", "send", target, message],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"Slack notification failed for '{channel.channel_name}': {result.stderr}", file=sys.stderr)
                return False
            return True
        except Exception as e:
            print(f"Slack notification error for '{channel.channel_name}': {e}", file=sys.stderr)
            return False

    def _send_email(self, to: str, subject: str, body: str) -> bool:
        """Send email notification.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body

        Returns:
            True if sent successfully
        """
        try:
            result = subprocess.run(
                [
                    "google", "gmail", "send",
                    "--to", to,
                    "--subject", subject,
                    "--body", body,
                    "--confirm",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"Email notification failed: {result.stderr}", file=sys.stderr)
                return False
            return True
        except Exception as e:
            print(f"Email notification error: {e}", file=sys.stderr)
            return False

    def _send_macos(self, channel: MacosNotificationChannel, title: str, message: str) -> bool:
        """Send macOS desktop notification.

        Args:
            channel: Macos notification channel configuration
            title: Notification title
            message: Notification message

        Returns:
            True if sent successfully
        """
        try:
            cmd = [
                "notifier", "send",
                "--title", title,
                "--message", message,
            ]

            if channel.sound:
                cmd.extend(["--sound", channel.sound])

            if channel.ignore_dnd:
                cmd.append("--ignore-dnd")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"Macos notification failed for '{channel.channel_name}': {result.stderr}", file=sys.stderr)
                return False
            return True
        except Exception as e:
            print(f"Macos notification error for '{channel.channel_name}': {e}", file=sys.stderr)
            return False
