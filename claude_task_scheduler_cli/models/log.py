"""Pydantic models for task activity logs."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from .base import CLIModel


class LogLevel(str, Enum):
    """Log severity level."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogEventType(str, Enum):
    """Types of events that can be logged."""

    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    TASK_RETRY = "task_retry"
    COMMAND_EXECUTED = "command_executed"
    OUTPUT_CAPTURED = "output_captured"


class TaskLog(CLIModel):
    """A single log entry for task activity."""

    id: str = Field(frozen=True)
    task_id: str = Field(frozen=True)
    run_id: Optional[str] = Field(default=None, frozen=True)
    event_type: LogEventType
    level: LogLevel = LogLevel.INFO
    message: str
    details: Optional[str] = None  # Full output, no truncation
    created_at: datetime = Field(frozen=True)


class TaskLogDetail(TaskLog):
    """Task log with joined context from task and run."""

    task_name: Optional[str] = None
    run_attempt: Optional[int] = None


class TaskLogCreate(CLIModel):
    """Model for creating a task log entry."""

    task_id: str
    run_id: Optional[str] = None
    event_type: LogEventType
    level: LogLevel = LogLevel.INFO
    message: str
    details: Optional[str] = None
