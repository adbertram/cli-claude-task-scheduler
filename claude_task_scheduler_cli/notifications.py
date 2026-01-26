"""Notification service for task execution events."""

import subprocess
import sys
from typing import Optional

from .db_client import DatabaseClient
from .output import prettify_output
from .models.notification import (
    GmailNotificationChannel,
    MacosNotificationChannel,
    SlackDeliveryMethod,
    SlackNotificationChannel,
)
from .models.task import (
    NotificationConfig,
    NotifyOn,
    RunStatus,
    ScheduledTask,
    ScheduledTaskDetail,
    TaskOutcome,
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
        if not config or NotifyOn.TASK_START not in config.notify_on:
            return

        message = self._format_start_message(task, run)
        self._send(config, f"Task Started: {task.name}", message)

    def notify_end(self, task: ScheduledTask | ScheduledTaskDetail, run: TaskRun) -> None:
        """Send notification when task ends.

        Checks for TASK_END on success, TASK_ERROR on failure.
        A task that ran successfully (exit_code=0) but failed semantically
        (task_outcome=FAILED) is treated as a failure for notification purposes.

        Args:
            task: The scheduled task
            run: The task run record
        """
        config = self._get_config(task)
        if not config:
            return

        # Determine if this is a success or failure
        is_failure = (
            run.status != RunStatus.SUCCESS or
            run.task_outcome == TaskOutcome.FAILED
        )

        # Check if we should send notification based on notify_on config
        if is_failure:
            if NotifyOn.TASK_ERROR not in config.notify_on:
                return
        else:
            if NotifyOn.TASK_END not in config.notify_on:
                return

        message = self._format_end_message(task, run)

        # Determine subject based on status
        if run.status == RunStatus.SUCCESS:
            if run.task_outcome == TaskOutcome.FAILED:
                subject = f"Task Failed (Semantic): {task.name}"
            else:
                subject = f"Task Completed: {task.name}"
        else:
            subject = f"Task Failed: {task.name}"

        self._send(config, subject, message)

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

    def _format_end_message(self, task: ScheduledTask, run: TaskRun) -> str:
        """Format end notification message (success or failure)."""
        # Determine overall status
        if run.status == RunStatus.SUCCESS:
            if run.task_outcome == TaskOutcome.FAILED:
                status = "Failed (Semantic)"
                reason = run.task_outcome_reason or "Task reported failure"
            else:
                status = "Completed"
                reason = None
        elif run.status == RunStatus.TIMEOUT:
            status = "Timeout"
            reason = f"Timed out after {task.timeout_seconds}s"
        else:
            status = "Failed"
            reason = run.error_message or "Unknown error"

        lines = [
            f"Task: {task.name}",
            f"Status: {status}",
            f"Run ID: {run.id}",
            f"Attempt: {run.attempt_number}/{task.max_retries}",
            f"Session ID: {run.session_id or 'N/A'}",
        ]

        if reason:
            lines.append(f"Reason: {reason}")

        # Add prettified output summary
        if run.output:
            extracted = prettify_output(run.output)
            result = extracted.get("result", "")
            if result:
                # Truncate for notification
                if len(result) > 500:
                    result = result[:500] + "..."
                lines.append(f"Output: {result}")

            # Add cost if available
            if extracted.get("cost_usd"):
                lines.append(f"Cost: ${extracted['cost_usd']:.4f}")

        return "\n".join(lines)

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
