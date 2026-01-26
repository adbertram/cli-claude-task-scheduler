"""SQLAlchemy database models for the scheduler."""

from datetime import datetime
from typing import Optional
import json

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

# Junction tables for many-to-many relationships
task_slack_channels = Table(
    "task_slack_channels",
    Base.metadata,
    Column("task_id", String, ForeignKey("scheduled_tasks.id"), primary_key=True),
    Column("slack_channel_id", String, ForeignKey("slack_notification_channels.id"), primary_key=True),
)

task_gmail_channels = Table(
    "task_gmail_channels",
    Base.metadata,
    Column("task_id", String, ForeignKey("scheduled_tasks.id"), primary_key=True),
    Column("gmail_channel_id", String, ForeignKey("gmail_notification_channels.id"), primary_key=True),
)

task_macos_channels = Table(
    "task_macos_channels",
    Base.metadata,
    Column("task_id", String, ForeignKey("scheduled_tasks.id"), primary_key=True),
    Column("macos_channel_id", String, ForeignKey("macos_notification_channels.id"), primary_key=True),
)


class ScheduledTaskDB(Base):
    """Database model for scheduled tasks."""

    __tablename__ = "scheduled_tasks"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    project_path = Column(String, nullable=False)
    cron_expression = Column(String, nullable=False)
    model = Column(String, nullable=False)
    max_retries = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=3600)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    runs = relationship("TaskRunDB", back_populates="task", cascade="all, delete-orphan")
    logs = relationship("TaskLogDB", back_populates="task", cascade="all, delete-orphan")
    notification_config = relationship(
        "NotificationConfigDB",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
    )
    slack_channels = relationship(
        "SlackNotificationChannelDB",
        secondary=task_slack_channels,
        back_populates="tasks",
    )
    gmail_channels = relationship(
        "GmailNotificationChannelDB",
        secondary=task_gmail_channels,
        back_populates="tasks",
    )
    macos_channels = relationship(
        "MacosNotificationChannelDB",
        secondary=task_macos_channels,
        back_populates="tasks",
    )


class TaskRunDB(Base):
    """Database model for task execution runs."""

    __tablename__ = "task_runs"

    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("scheduled_tasks.id"), nullable=False)
    status = Column(String, nullable=False)  # running, success, failure, timeout
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    session_id = Column(String, nullable=True)
    exit_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    output = Column(Text, nullable=False)
    attempt_number = Column(Integer, default=1)
    task_outcome = Column(String, nullable=False, default="unknown")  # success, failed, unknown
    task_outcome_reason = Column(Text, nullable=True)

    # Relationships
    task = relationship("ScheduledTaskDB", back_populates="runs")
    logs = relationship("TaskLogDB", back_populates="run", cascade="all, delete-orphan")


class NotificationConfigDB(Base):
    """Database model for notification configuration."""

    __tablename__ = "notification_configs"

    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("scheduled_tasks.id"), unique=True, nullable=False)
    events_json = Column(Text, default='["running", "success", "failure"]')

    # Relationships
    task = relationship("ScheduledTaskDB", back_populates="notification_config")

    @property
    def events(self) -> list[str]:
        """Parse events from JSON."""
        return json.loads(self.events_json) if self.events_json else []

    @events.setter
    def events(self, value: list[str]) -> None:
        """Serialize events to JSON."""
        self.events_json = json.dumps(value)


class SlackNotificationChannelDB(Base):
    """Database model for Slack notification channels (standalone)."""

    __tablename__ = "slack_notification_channels"

    id = Column(String, primary_key=True)
    channel_name = Column(String, nullable=False, default="Slack DM")
    enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    workspace_id = Column(String, default="T0F2BD3QA")  # ATA Learning workspace
    delivery_method = Column(String, nullable=False, default="direct_message")
    delivery_channel_id = Column(String, nullable=True)
    delivery_user_id = Column(String, default="U01RZG11N9K")  # adbertram

    # Relationships (many-to-many with tasks)
    tasks = relationship(
        "ScheduledTaskDB",
        secondary=task_slack_channels,
        back_populates="slack_channels",
    )


class GmailNotificationChannelDB(Base):
    """Database model for Gmail notification channels (standalone)."""

    __tablename__ = "gmail_notification_channels"

    id = Column(String, primary_key=True)
    channel_name = Column(String, nullable=False, default="Email")
    enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    email_address = Column(String, nullable=False, default="adbertram@gmail.com")

    # Relationships (many-to-many with tasks)
    tasks = relationship(
        "ScheduledTaskDB",
        secondary=task_gmail_channels,
        back_populates="gmail_channels",
    )


class MacosNotificationChannelDB(Base):
    """Database model for macOS desktop notification channels (standalone)."""

    __tablename__ = "macos_notification_channels"

    id = Column(String, primary_key=True)
    channel_name = Column(String, nullable=False, default="Desktop")
    enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    sound = Column(String, nullable=True)
    ignore_dnd = Column(Boolean, default=False)

    # Relationships (many-to-many with tasks)
    tasks = relationship(
        "ScheduledTaskDB",
        secondary=task_macos_channels,
        back_populates="macos_channels",
    )


class TaskLogDB(Base):
    """Database model for task activity logs."""

    __tablename__ = "task_logs"

    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("scheduled_tasks.id"), nullable=False)
    run_id = Column(String, ForeignKey("task_runs.id"), nullable=True)
    event_type = Column(String, nullable=False)
    level = Column(String, nullable=False, default="info")
    message = Column(String, nullable=False)
    details = Column(Text, nullable=True)  # Full output, no truncation
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    task = relationship("ScheduledTaskDB", back_populates="logs")
    run = relationship("TaskRunDB", back_populates="logs")


def get_engine(db_path: str = None):
    """Create database engine."""
    if db_path is None:
        import os
        db_dir = os.path.expanduser("~/.claude-task-scheduler")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "scheduler.db")

    return create_engine(f"sqlite:///{db_path}", echo=False)


def get_session(engine=None):
    """Create database session."""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_db(engine=None):
    """Initialize database tables."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)
    return engine


def _run_migrations(engine):
    """Run database migrations for schema updates.

    This handles adding new columns to existing tables without dropping data.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)

    # Check if task_runs table exists
    if "task_runs" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("task_runs")}

        # Add task_outcome column if missing
        if "task_outcome" not in columns:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE task_runs ADD COLUMN task_outcome VARCHAR DEFAULT 'unknown' NOT NULL"
                ))
                conn.commit()

        # Add task_outcome_reason column if missing
        if "task_outcome_reason" not in columns:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE task_runs ADD COLUMN task_outcome_reason TEXT"
                ))
                conn.commit()
