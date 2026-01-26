"""Database client for scheduled tasks and runs."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models.db import (
    GmailNotificationChannelDB,
    NotificationConfigDB,
    MacosNotificationChannelDB,
    ScheduledTaskDB,
    SlackNotificationChannelDB,
    TaskLogDB,
    TaskRunDB,
    get_engine,
    get_session,
    init_db,
    task_gmail_channels,
    task_macos_channels,
    task_slack_channels,
)
from .models.log import (
    LogEventType,
    LogLevel,
    TaskLog,
    TaskLogCreate,
    TaskLogDetail,
)
from .models.notification import (
    GmailNotificationChannel,
    MacosNotificationChannel,
    SlackDeliveryMethod,
    SlackDeliveryTarget,
    SlackNotificationChannel,
)
from .models.task import (
    NotificationConfig,
    NotificationEvent,
    ScheduledTask,
    ScheduledTaskCreate,
    ScheduledTaskDetail,
    ScheduledTaskUpdate,
    TaskRun,
    TaskRunDetail,
    TaskStatus,
)


class DatabaseClient:
    """Client for database operations on tasks and runs."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the database client.

        Args:
            db_path: Optional path to SQLite database. Defaults to ~/.claude-task-scheduler/scheduler.db
        """
        self.engine = get_engine(db_path)
        init_db(self.engine)

    def _get_session(self) -> Session:
        """Get a new database session."""
        return get_session(self.engine)

    # Task operations

    def create_task(self, data: ScheduledTaskCreate) -> ScheduledTaskDetail:
        """Create a new scheduled task.

        No channels are auto-assigned. Use slack_channel_ids/gmail_channel_ids to assign channels.
        """
        session = self._get_session()
        try:
            task_id = str(uuid.uuid4())
            now = datetime.utcnow()

            task_db = ScheduledTaskDB(
                id=task_id,
                name=data.name,
                prompt=data.prompt,
                project_path=data.project_path,
                cron_expression=data.cron_expression,
                model=data.model,
                max_retries=data.max_retries,
                enabled=data.enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(task_db)

            # Create notification config
            notif_id = str(uuid.uuid4())
            notif_db = NotificationConfigDB(
                id=notif_id,
                task_id=task_id,
                events_json=str([e.value for e in data.notification_events]).replace("'", '"'),
            )
            session.add(notif_db)

            # Assign Slack channels by ID
            slack_channels_db = []
            for channel_id in (data.slack_channel_ids or []):
                channel_db = session.query(SlackNotificationChannelDB).filter_by(id=channel_id).first()
                if channel_db:
                    task_db.slack_channels.append(channel_db)
                    slack_channels_db.append(channel_db)

            # Assign Gmail channels by ID
            gmail_channels_db = []
            for channel_id in (data.gmail_channel_ids or []):
                channel_db = session.query(GmailNotificationChannelDB).filter_by(id=channel_id).first()
                if channel_db:
                    task_db.gmail_channels.append(channel_db)
                    gmail_channels_db.append(channel_db)

            # Assign Macos channels by ID
            macos_channels_db = []
            for channel_id in (data.macos_channel_ids or []):
                channel_db = session.query(MacosNotificationChannelDB).filter_by(id=channel_id).first()
                if channel_db:
                    task_db.macos_channels.append(channel_db)
                    macos_channels_db.append(channel_db)

            session.commit()
            session.refresh(task_db)
            session.refresh(notif_db)

            return self._task_db_to_detail(task_db, notif_db, slack_channels_db, gmail_channels_db, macos_channels_db)
        finally:
            session.close()

    def get_task(self, task_id: str) -> Optional[ScheduledTaskDetail]:
        """Get a task by ID."""
        session = self._get_session()
        try:
            task_db = session.query(ScheduledTaskDB).filter_by(id=task_id).first()
            if not task_db:
                return None
            notif_db = session.query(NotificationConfigDB).filter_by(task_id=task_id).first()
            # Get channels via relationships (junction tables)
            slack_channels_db = task_db.slack_channels
            gmail_channels_db = task_db.gmail_channels
            macos_channels_db = task_db.macos_channels
            return self._task_db_to_detail(task_db, notif_db, slack_channels_db, gmail_channels_db, macos_channels_db)
        finally:
            session.close()

    def list_tasks(
        self,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[ScheduledTaskDetail]:
        """List all tasks with notification details."""
        session = self._get_session()
        try:
            query = session.query(ScheduledTaskDB)
            if enabled_only:
                query = query.filter_by(enabled=True)
            query = query.order_by(ScheduledTaskDB.created_at.desc()).limit(limit)
            tasks_db = query.all()

            result = []
            for task_db in tasks_db:
                notif_db = session.query(NotificationConfigDB).filter_by(task_id=task_db.id).first()
                slack_channels_db = task_db.slack_channels
                gmail_channels_db = task_db.gmail_channels
                macos_channels_db = task_db.macos_channels
                result.append(self._task_db_to_detail(task_db, notif_db, slack_channels_db, gmail_channels_db, macos_channels_db))
            return result
        finally:
            session.close()

    def update_task(self, task_id: str, data: ScheduledTaskUpdate) -> Optional[ScheduledTaskDetail]:
        """Update a task."""
        session = self._get_session()
        try:
            task_db = session.query(ScheduledTaskDB).filter_by(id=task_id).first()
            if not task_db:
                return None

            # Update task fields
            update_data = data.model_dump(
                exclude_none=True,
                exclude={"notification_events", "slack_channel_ids", "gmail_channel_ids", "macos_channel_ids"},
            )
            for key, value in update_data.items():
                setattr(task_db, key, value)
            task_db.updated_at = datetime.utcnow()

            # Update notification config
            notif_db = session.query(NotificationConfigDB).filter_by(task_id=task_id).first()
            if notif_db and data.notification_events is not None:
                notif_db.events_json = str([e.value for e in data.notification_events]).replace("'", '"')

            # Update Slack channel assignments (replace all if provided)
            if data.slack_channel_ids is not None:
                # Clear existing associations
                task_db.slack_channels.clear()
                # Add new associations
                for channel_id in data.slack_channel_ids:
                    channel_db = session.query(SlackNotificationChannelDB).filter_by(id=channel_id).first()
                    if channel_db:
                        task_db.slack_channels.append(channel_db)

            # Update Gmail channel assignments (replace all if provided)
            if data.gmail_channel_ids is not None:
                # Clear existing associations
                task_db.gmail_channels.clear()
                # Add new associations
                for channel_id in data.gmail_channel_ids:
                    channel_db = session.query(GmailNotificationChannelDB).filter_by(id=channel_id).first()
                    if channel_db:
                        task_db.gmail_channels.append(channel_db)

            # Update Macos channel assignments (replace all if provided)
            if data.macos_channel_ids is not None:
                # Clear existing associations
                task_db.macos_channels.clear()
                # Add new associations
                for channel_id in data.macos_channel_ids:
                    channel_db = session.query(MacosNotificationChannelDB).filter_by(id=channel_id).first()
                    if channel_db:
                        task_db.macos_channels.append(channel_db)

            session.commit()
            session.refresh(task_db)
            if notif_db:
                session.refresh(notif_db)

            # Get channels via relationships
            slack_channels_db = task_db.slack_channels
            gmail_channels_db = task_db.gmail_channels
            macos_channels_db = task_db.macos_channels

            return self._task_db_to_detail(task_db, notif_db, slack_channels_db, gmail_channels_db, macos_channels_db)
        finally:
            session.close()

    def delete_task(self, task_id: str) -> bool:
        """Delete a task and all associated data."""
        session = self._get_session()
        try:
            task_db = session.query(ScheduledTaskDB).filter_by(id=task_id).first()
            if not task_db:
                return False
            session.delete(task_db)
            session.commit()
            return True
        finally:
            session.close()

    def enable_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Enable a task."""
        return self._set_task_enabled(task_id, True)

    def disable_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Disable a task."""
        return self._set_task_enabled(task_id, False)

    def _set_task_enabled(self, task_id: str, enabled: bool) -> Optional[ScheduledTask]:
        """Set task enabled status."""
        session = self._get_session()
        try:
            task_db = session.query(ScheduledTaskDB).filter_by(id=task_id).first()
            if not task_db:
                return None
            task_db.enabled = enabled
            task_db.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(task_db)
            return self._task_db_to_model(task_db)
        finally:
            session.close()

    # Run operations

    def create_run(
        self,
        task_id: str,
        attempt_number: int = 1,
    ) -> TaskRun:
        """Create a new task run."""
        session = self._get_session()
        try:
            run_id = str(uuid.uuid4())
            now = datetime.utcnow()

            run_db = TaskRunDB(
                id=run_id,
                task_id=task_id,
                status=TaskStatus.RUNNING.value,
                started_at=now,
                attempt_number=attempt_number,
            )
            session.add(run_db)
            session.commit()
            session.refresh(run_db)

            return self._run_db_to_model(run_db)
        finally:
            session.close()

    def get_run(self, run_id: str) -> Optional[TaskRunDetail]:
        """Get a run by ID with task details."""
        session = self._get_session()
        try:
            run_db = session.query(TaskRunDB).filter_by(id=run_id).first()
            if not run_db:
                return None
            task_db = session.query(ScheduledTaskDB).filter_by(id=run_db.task_id).first()
            return self._run_db_to_detail(run_db, task_db)
        finally:
            session.close()

    def list_runs(
        self,
        task_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> list[TaskRun]:
        """List runs with optional filters."""
        session = self._get_session()
        try:
            query = session.query(TaskRunDB)
            if task_id:
                query = query.filter_by(task_id=task_id)
            if status:
                query = query.filter_by(status=status.value)
            query = query.order_by(TaskRunDB.started_at.desc()).limit(limit)
            runs_db = query.all()
            return [self._run_db_to_model(r) for r in runs_db]
        finally:
            session.close()

    def update_run(
        self,
        run_id: str,
        status: Optional[TaskStatus] = None,
        session_id: Optional[str] = None,
        exit_code: Optional[int] = None,
        error_message: Optional[str] = None,
        summary: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[TaskRun]:
        """Update a run."""
        session = self._get_session()
        try:
            run_db = session.query(TaskRunDB).filter_by(id=run_id).first()
            if not run_db:
                return None

            if status is not None:
                run_db.status = status.value
            if session_id is not None:
                run_db.session_id = session_id
            if exit_code is not None:
                run_db.exit_code = exit_code
            if error_message is not None:
                run_db.error_message = error_message
            if summary is not None:
                run_db.summary = summary
            if completed_at is not None:
                run_db.completed_at = completed_at

            session.commit()
            session.refresh(run_db)

            return self._run_db_to_model(run_db)
        finally:
            session.close()

    def get_incomplete_runs(self) -> list[TaskRun]:
        """Get all runs with RUNNING status (for resume on restart)."""
        session = self._get_session()
        try:
            runs_db = session.query(TaskRunDB).filter_by(status=TaskStatus.RUNNING.value).all()
            return [self._run_db_to_model(r) for r in runs_db]
        finally:
            session.close()

    def count_runs(self, task_id: str) -> int:
        """Count total runs for a task."""
        session = self._get_session()
        try:
            return session.query(TaskRunDB).filter_by(task_id=task_id).count()
        finally:
            session.close()

    def get_notification_config(self, task_id: str) -> Optional[NotificationConfig]:
        """Get notification config for a task."""
        session = self._get_session()
        try:
            task_db = session.query(ScheduledTaskDB).filter_by(id=task_id).first()
            if not task_db:
                return None
            notif_db = session.query(NotificationConfigDB).filter_by(task_id=task_id).first()
            if not notif_db:
                return None
            # Get channels via relationships (junction tables)
            slack_channels_db = task_db.slack_channels
            gmail_channels_db = task_db.gmail_channels
            macos_channels_db = task_db.macos_channels
            return self._notif_db_to_model(notif_db, slack_channels_db, gmail_channels_db, macos_channels_db)
        finally:
            session.close()

    # Conversion helpers

    def _task_db_to_model(self, task_db: ScheduledTaskDB) -> ScheduledTask:
        """Convert DB task to Pydantic model."""
        return ScheduledTask(
            id=task_db.id,
            name=task_db.name,
            prompt=task_db.prompt,
            project_path=task_db.project_path,
            cron_expression=task_db.cron_expression,
            model=task_db.model,
            max_retries=task_db.max_retries,
            enabled=task_db.enabled,
            created_at=task_db.created_at,
            updated_at=task_db.updated_at,
        )

    def _task_db_to_detail(
        self,
        task_db: ScheduledTaskDB,
        notif_db: Optional[NotificationConfigDB],
        slack_channels_db: list[SlackNotificationChannelDB] = None,
        gmail_channels_db: list[GmailNotificationChannelDB] = None,
        macos_channels_db: list[MacosNotificationChannelDB] = None,
    ) -> ScheduledTaskDetail:
        """Convert DB task to detail model with notification config."""
        slack_channels_db = slack_channels_db or []
        gmail_channels_db = gmail_channels_db or []
        macos_channels_db = macos_channels_db or []
        notif = self._notif_db_to_model(notif_db, slack_channels_db, gmail_channels_db, macos_channels_db) if notif_db else None
        return ScheduledTaskDetail(
            id=task_db.id,
            name=task_db.name,
            prompt=task_db.prompt,
            project_path=task_db.project_path,
            cron_expression=task_db.cron_expression,
            model=task_db.model,
            max_retries=task_db.max_retries,
            enabled=task_db.enabled,
            created_at=task_db.created_at,
            updated_at=task_db.updated_at,
            notification_config=notif,
        )

    def _run_db_to_model(self, run_db: TaskRunDB) -> TaskRun:
        """Convert DB run to Pydantic model."""
        return TaskRun(
            id=run_db.id,
            task_id=run_db.task_id,
            status=TaskStatus(run_db.status),
            started_at=run_db.started_at,
            completed_at=run_db.completed_at,
            session_id=run_db.session_id,
            exit_code=run_db.exit_code,
            error_message=run_db.error_message,
            summary=run_db.summary,
            attempt_number=run_db.attempt_number,
        )

    def _run_db_to_detail(
        self,
        run_db: TaskRunDB,
        task_db: Optional[ScheduledTaskDB],
    ) -> TaskRunDetail:
        """Convert DB run to detail model with task name."""
        return TaskRunDetail(
            id=run_db.id,
            task_id=run_db.task_id,
            status=TaskStatus(run_db.status),
            started_at=run_db.started_at,
            completed_at=run_db.completed_at,
            session_id=run_db.session_id,
            exit_code=run_db.exit_code,
            error_message=run_db.error_message,
            summary=run_db.summary,
            attempt_number=run_db.attempt_number,
            task_name=task_db.name if task_db else None,
        )

    def _notif_db_to_model(
        self,
        notif_db: NotificationConfigDB,
        slack_channels_db: list[SlackNotificationChannelDB] = None,
        gmail_channels_db: list[GmailNotificationChannelDB] = None,
        macos_channels_db: list[MacosNotificationChannelDB] = None,
    ) -> NotificationConfig:
        """Convert DB notification config to Pydantic model."""
        slack_channels_db = slack_channels_db or []
        gmail_channels_db = gmail_channels_db or []
        macos_channels_db = macos_channels_db or []
        events = [NotificationEvent(e) for e in notif_db.events]
        slack_channels = [self._slack_channel_db_to_model(ch) for ch in slack_channels_db]
        gmail_channels = [self._gmail_channel_db_to_model(ch) for ch in gmail_channels_db]
        macos_channels = [self._macos_channel_db_to_model(ch) for ch in macos_channels_db]
        return NotificationConfig(
            id=notif_db.id,
            task_id=notif_db.task_id,
            events=events,
            slack_channels=slack_channels,
            gmail_channels=gmail_channels,
            macos_channels=macos_channels,
        )

    def _slack_channel_db_to_model(self, channel_db: SlackNotificationChannelDB) -> SlackNotificationChannel:
        """Convert DB Slack channel to Pydantic model."""
        delivery = SlackDeliveryTarget(
            method=SlackDeliveryMethod(channel_db.delivery_method),
            channel_id=channel_db.delivery_channel_id,
            user_id=channel_db.delivery_user_id,
        )
        return SlackNotificationChannel(
            id=channel_db.id,
            channel_name=channel_db.channel_name,
            enabled=channel_db.enabled,
            is_default=channel_db.is_default,
            workspace_id=channel_db.workspace_id,
            delivery=delivery,
        )

    def _gmail_channel_db_to_model(self, channel_db: GmailNotificationChannelDB) -> GmailNotificationChannel:
        """Convert DB Gmail channel to Pydantic model."""
        return GmailNotificationChannel(
            id=channel_db.id,
            channel_name=channel_db.channel_name,
            enabled=channel_db.enabled,
            is_default=channel_db.is_default,
            email_address=channel_db.email_address,
        )

    def _macos_channel_db_to_model(self, channel_db: MacosNotificationChannelDB) -> MacosNotificationChannel:
        """Convert DB Macos channel to Pydantic model."""
        return MacosNotificationChannel(
            id=channel_db.id,
            channel_name=channel_db.channel_name,
            enabled=channel_db.enabled,
            is_default=channel_db.is_default,
            sound=channel_db.sound,
            ignore_dnd=channel_db.ignore_dnd,
        )

    # Slack channel operations

    def create_slack_channel(
        self,
        data: "SlackChannelCreate",
    ) -> SlackNotificationChannel:
        """Create a new Slack notification channel (standalone)."""
        from .models.task import SlackChannelCreate

        session = self._get_session()
        try:
            channel_id = str(uuid.uuid4())
            slack_kwargs = {"id": channel_id, "enabled": data.enabled, "is_default": data.is_default}
            if data.channel_name is not None:
                slack_kwargs["channel_name"] = data.channel_name
            if data.workspace_id is not None:
                slack_kwargs["workspace_id"] = data.workspace_id
            if data.delivery_method is not None:
                slack_kwargs["delivery_method"] = data.delivery_method
            if data.delivery_channel_id is not None:
                slack_kwargs["delivery_channel_id"] = data.delivery_channel_id
            if data.delivery_user_id is not None:
                slack_kwargs["delivery_user_id"] = data.delivery_user_id

            channel_db = SlackNotificationChannelDB(**slack_kwargs)
            session.add(channel_db)
            session.commit()
            session.refresh(channel_db)
            return self._slack_channel_db_to_model(channel_db)
        finally:
            session.close()

    def get_slack_channel(self, channel_id: str) -> Optional[SlackNotificationChannel]:
        """Get a Slack channel by ID."""
        session = self._get_session()
        try:
            channel_db = session.query(SlackNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return None
            return self._slack_channel_db_to_model(channel_db)
        finally:
            session.close()

    def list_slack_channels(self) -> list[SlackNotificationChannel]:
        """List all Slack channels."""
        session = self._get_session()
        try:
            channels_db = session.query(SlackNotificationChannelDB).all()
            return [self._slack_channel_db_to_model(ch) for ch in channels_db]
        finally:
            session.close()

    def update_slack_channel(
        self,
        channel_id: str,
        channel_name: Optional[str] = None,
        enabled: Optional[bool] = None,
        workspace_id: Optional[str] = None,
        delivery_method: Optional[str] = None,
        delivery_channel_id: Optional[str] = None,
        delivery_user_id: Optional[str] = None,
    ) -> Optional[SlackNotificationChannel]:
        """Update a Slack channel."""
        session = self._get_session()
        try:
            channel_db = session.query(SlackNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return None

            if channel_name is not None:
                channel_db.channel_name = channel_name
            if enabled is not None:
                channel_db.enabled = enabled
            if workspace_id is not None:
                channel_db.workspace_id = workspace_id
            if delivery_method is not None:
                channel_db.delivery_method = delivery_method
            if delivery_channel_id is not None:
                channel_db.delivery_channel_id = delivery_channel_id
            if delivery_user_id is not None:
                channel_db.delivery_user_id = delivery_user_id

            session.commit()
            session.refresh(channel_db)
            return self._slack_channel_db_to_model(channel_db)
        finally:
            session.close()

    def delete_slack_channel(self, channel_id: str) -> bool:
        """Delete a Slack channel."""
        session = self._get_session()
        try:
            channel_db = session.query(SlackNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return False
            session.delete(channel_db)
            session.commit()
            return True
        finally:
            session.close()

    # Gmail channel operations

    def create_gmail_channel(
        self,
        data: "GmailChannelCreate",
    ) -> GmailNotificationChannel:
        """Create a new Gmail notification channel (standalone)."""
        from .models.task import GmailChannelCreate

        session = self._get_session()
        try:
            channel_id = str(uuid.uuid4())
            gmail_kwargs = {"id": channel_id, "enabled": data.enabled, "is_default": data.is_default}
            if data.channel_name is not None:
                gmail_kwargs["channel_name"] = data.channel_name
            if data.email_address is not None:
                gmail_kwargs["email_address"] = data.email_address

            channel_db = GmailNotificationChannelDB(**gmail_kwargs)
            session.add(channel_db)
            session.commit()
            session.refresh(channel_db)
            return self._gmail_channel_db_to_model(channel_db)
        finally:
            session.close()

    def get_gmail_channel(self, channel_id: str) -> Optional[GmailNotificationChannel]:
        """Get a Gmail channel by ID."""
        session = self._get_session()
        try:
            channel_db = session.query(GmailNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return None
            return self._gmail_channel_db_to_model(channel_db)
        finally:
            session.close()

    def list_gmail_channels(self) -> list[GmailNotificationChannel]:
        """List all Gmail channels."""
        session = self._get_session()
        try:
            channels_db = session.query(GmailNotificationChannelDB).all()
            return [self._gmail_channel_db_to_model(ch) for ch in channels_db]
        finally:
            session.close()

    def update_gmail_channel(
        self,
        channel_id: str,
        channel_name: Optional[str] = None,
        enabled: Optional[bool] = None,
        email_address: Optional[str] = None,
    ) -> Optional[GmailNotificationChannel]:
        """Update a Gmail channel."""
        session = self._get_session()
        try:
            channel_db = session.query(GmailNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return None

            if channel_name is not None:
                channel_db.channel_name = channel_name
            if enabled is not None:
                channel_db.enabled = enabled
            if email_address is not None:
                channel_db.email_address = email_address

            session.commit()
            session.refresh(channel_db)
            return self._gmail_channel_db_to_model(channel_db)
        finally:
            session.close()

    def delete_gmail_channel(self, channel_id: str) -> bool:
        """Delete a Gmail channel."""
        session = self._get_session()
        try:
            channel_db = session.query(GmailNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return False
            session.delete(channel_db)
            session.commit()
            return True
        finally:
            session.close()

    # Macos channel operations

    def create_macos_channel(
        self,
        data: "MacosChannelCreate",
    ) -> MacosNotificationChannel:
        """Create a new Macos notification channel (standalone)."""
        from .models.task import MacosChannelCreate

        session = self._get_session()
        try:
            channel_id = str(uuid.uuid4())
            macos_kwargs = {"id": channel_id, "enabled": data.enabled, "is_default": data.is_default}
            if data.channel_name is not None:
                macos_kwargs["channel_name"] = data.channel_name
            if data.sound is not None:
                macos_kwargs["sound"] = data.sound
            if data.ignore_dnd is not None:
                macos_kwargs["ignore_dnd"] = data.ignore_dnd

            channel_db = MacosNotificationChannelDB(**macos_kwargs)
            session.add(channel_db)
            session.commit()
            session.refresh(channel_db)
            return self._macos_channel_db_to_model(channel_db)
        finally:
            session.close()

    def get_macos_channel(self, channel_id: str) -> Optional[MacosNotificationChannel]:
        """Get a Macos channel by ID."""
        session = self._get_session()
        try:
            channel_db = session.query(MacosNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return None
            return self._macos_channel_db_to_model(channel_db)
        finally:
            session.close()

    def list_macos_channels(self) -> list[MacosNotificationChannel]:
        """List all Macos channels."""
        session = self._get_session()
        try:
            channels_db = session.query(MacosNotificationChannelDB).all()
            return [self._macos_channel_db_to_model(ch) for ch in channels_db]
        finally:
            session.close()

    def update_macos_channel(
        self,
        channel_id: str,
        channel_name: Optional[str] = None,
        enabled: Optional[bool] = None,
        sound: Optional[str] = None,
        ignore_dnd: Optional[bool] = None,
    ) -> Optional[MacosNotificationChannel]:
        """Update a Macos channel."""
        session = self._get_session()
        try:
            channel_db = session.query(MacosNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return None

            if channel_name is not None:
                channel_db.channel_name = channel_name
            if enabled is not None:
                channel_db.enabled = enabled
            if sound is not None:
                channel_db.sound = sound
            if ignore_dnd is not None:
                channel_db.ignore_dnd = ignore_dnd

            session.commit()
            session.refresh(channel_db)
            return self._macos_channel_db_to_model(channel_db)
        finally:
            session.close()

    def delete_macos_channel(self, channel_id: str) -> bool:
        """Delete a Macos channel."""
        session = self._get_session()
        try:
            channel_db = session.query(MacosNotificationChannelDB).filter_by(id=channel_id).first()
            if not channel_db:
                return False
            session.delete(channel_db)
            session.commit()
            return True
        finally:
            session.close()

    # Default channel operations

    def get_default_slack_channels(self) -> list[SlackNotificationChannel]:
        """Get all Slack channels marked as default."""
        session = self._get_session()
        try:
            channels_db = session.query(SlackNotificationChannelDB).filter_by(is_default=True, enabled=True).all()
            return [self._slack_channel_db_to_model(ch) for ch in channels_db]
        finally:
            session.close()

    def get_default_gmail_channels(self) -> list[GmailNotificationChannel]:
        """Get all Gmail channels marked as default."""
        session = self._get_session()
        try:
            channels_db = session.query(GmailNotificationChannelDB).filter_by(is_default=True, enabled=True).all()
            return [self._gmail_channel_db_to_model(ch) for ch in channels_db]
        finally:
            session.close()

    def get_default_macos_channels(self) -> list[MacosNotificationChannel]:
        """Get all Macos channels marked as default."""
        session = self._get_session()
        try:
            channels_db = session.query(MacosNotificationChannelDB).filter_by(is_default=True, enabled=True).all()
            return [self._macos_channel_db_to_model(ch) for ch in channels_db]
        finally:
            session.close()

    # Log operations

    def create_log(
        self,
        task_id: str,
        event_type: LogEventType,
        message: str,
        level: LogLevel = LogLevel.INFO,
        run_id: Optional[str] = None,
        details: Optional[str] = None,
    ) -> TaskLog:
        """Create a new log entry.

        Args:
            task_id: ID of the task
            event_type: Type of event being logged
            message: Log message
            level: Log severity level
            run_id: Optional run ID if log is associated with a run
            details: Optional full details (no truncation)

        Returns:
            Created TaskLog
        """
        session = self._get_session()
        try:
            log_id = str(uuid.uuid4())
            now = datetime.utcnow()

            log_db = TaskLogDB(
                id=log_id,
                task_id=task_id,
                run_id=run_id,
                event_type=event_type.value,
                level=level.value,
                message=message,
                details=details,
                created_at=now,
            )
            session.add(log_db)
            session.commit()
            session.refresh(log_db)

            return self._log_db_to_model(log_db)
        finally:
            session.close()

    def get_log(self, log_id: str) -> Optional[TaskLogDetail]:
        """Get a log entry by ID with task and run details."""
        session = self._get_session()
        try:
            log_db = session.query(TaskLogDB).filter_by(id=log_id).first()
            if not log_db:
                return None
            task_db = session.query(ScheduledTaskDB).filter_by(id=log_db.task_id).first()
            run_db = session.query(TaskRunDB).filter_by(id=log_db.run_id).first() if log_db.run_id else None
            return self._log_db_to_detail(log_db, task_db, run_db)
        finally:
            session.close()

    def list_logs(
        self,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        event_type: Optional[LogEventType] = None,
        level: Optional[LogLevel] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskLog]:
        """List logs with optional filters.

        Args:
            task_id: Filter by task ID
            run_id: Filter by run ID
            event_type: Filter by event type
            level: Filter by minimum log level
            since: Filter logs after this time
            until: Filter logs before this time
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of TaskLog entries
        """
        session = self._get_session()
        try:
            query = session.query(TaskLogDB)

            if task_id:
                query = query.filter_by(task_id=task_id)
            if run_id:
                query = query.filter_by(run_id=run_id)
            if event_type:
                query = query.filter_by(event_type=event_type.value)
            if level:
                # Filter by level and higher severity
                level_order = ["debug", "info", "warning", "error"]
                level_idx = level_order.index(level.value)
                allowed_levels = level_order[level_idx:]
                query = query.filter(TaskLogDB.level.in_(allowed_levels))
            if since:
                query = query.filter(TaskLogDB.created_at >= since)
            if until:
                query = query.filter(TaskLogDB.created_at <= until)

            query = query.order_by(TaskLogDB.created_at.desc())
            query = query.offset(offset).limit(limit)

            logs_db = query.all()
            return [self._log_db_to_model(log) for log in logs_db]
        finally:
            session.close()

    def delete_logs(
        self,
        task_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        """Delete logs matching the criteria.

        Args:
            task_id: Delete logs for this task only
            before: Delete logs created before this time

        Returns:
            Number of logs deleted
        """
        session = self._get_session()
        try:
            query = session.query(TaskLogDB)

            if task_id:
                query = query.filter_by(task_id=task_id)
            if before:
                query = query.filter(TaskLogDB.created_at < before)

            count = query.count()
            query.delete(synchronize_session=False)
            session.commit()

            return count
        finally:
            session.close()

    def count_logs(
        self,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> int:
        """Count logs matching the criteria.

        Args:
            task_id: Count logs for this task
            run_id: Count logs for this run

        Returns:
            Number of logs
        """
        session = self._get_session()
        try:
            query = session.query(TaskLogDB)

            if task_id:
                query = query.filter_by(task_id=task_id)
            if run_id:
                query = query.filter_by(run_id=run_id)

            return query.count()
        finally:
            session.close()

    def _log_db_to_model(self, log_db: TaskLogDB) -> TaskLog:
        """Convert DB log to Pydantic model."""
        return TaskLog(
            id=log_db.id,
            task_id=log_db.task_id,
            run_id=log_db.run_id,
            event_type=LogEventType(log_db.event_type),
            level=LogLevel(log_db.level),
            message=log_db.message,
            details=log_db.details,
            created_at=log_db.created_at,
        )

    def _log_db_to_detail(
        self,
        log_db: TaskLogDB,
        task_db: Optional[ScheduledTaskDB],
        run_db: Optional[TaskRunDB],
    ) -> TaskLogDetail:
        """Convert DB log to detail model with task and run info."""
        return TaskLogDetail(
            id=log_db.id,
            task_id=log_db.task_id,
            run_id=log_db.run_id,
            event_type=LogEventType(log_db.event_type),
            level=LogLevel(log_db.level),
            message=log_db.message,
            details=log_db.details,
            created_at=log_db.created_at,
            task_name=task_db.name if task_db else None,
            run_attempt=run_db.attempt_number if run_db else None,
        )
