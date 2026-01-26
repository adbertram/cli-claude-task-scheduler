"""Output formatting helpers.

Stream Usage:
    stdout (fd 1) → Data only (JSON, tables) - via print_json(), print_table()
    stderr (fd 2) → Messages only - via print_error(), print_warning(), print_success(), print_info()

This separation enables clean piping: `claude-task-scheduler list | jq '.field'`
"""
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from rich import box


# Rich console for table output
console = Console()


def _utc_to_local(dt: datetime) -> datetime:
    """Convert a naive UTC datetime to local time."""
    # Treat naive datetime as UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Convert to local time
    return dt.astimezone()


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    """Try to parse an ISO datetime string."""
    # Common ISO formats from Pydantic serialization
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f",  # 2024-01-15T10:30:00.123456
        "%Y-%m-%dT%H:%M:%S",     # 2024-01-15T10:30:00
        "%Y-%m-%d %H:%M:%S.%f",  # 2024-01-15 10:30:00.123456
        "%Y-%m-%d %H:%M:%S",     # 2024-01-15 10:30:00
    ]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _format_cell_value(value: Any) -> str:
    """
    Format a cell value for table display.

    Args:
        value: The value to format

    Returns:
        String representation suitable for table display
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, datetime):
        local_dt = _utc_to_local(value)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, str):
        # Try to parse ISO datetime strings and convert to local time
        dt = _parse_iso_datetime(value)
        if dt is not None:
            local_dt = _utc_to_local(dt)
            return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def print_table(
    data: Optional[Union[Sequence[Union[BaseModel, dict]], dict]],
    columns: Optional[List[str]] = None,
    headers: Optional[List[str]] = None,
    title: Optional[str] = None
):
    """
    Print data as a Rich formatted table to stdout.

    Handles Pydantic models, dicts, and lists of either.
    Uses Rich tables with box-drawing characters for better visual output.
    Limits display to max 6 columns for readability.

    Args:
        data: Data to output as table (list of dicts/models or single dict/model)
        columns: Optional list of column keys to display. If None, auto-discovers from data.
        headers: Optional display headers (defaults to column names)
        title: Optional table title
    """
    if data is None:
        console.print("[dim]No data[/dim]")
        return

    # Handle wrapped responses (e.g., {items: [...], total: N})
    if isinstance(data, dict) and 'items' in data and isinstance(data['items'], list):
        data = data['items']

    # Convert single item to list
    if isinstance(data, (dict, BaseModel)):
        data = [data]

    if not data:
        console.print("[dim]No data[/dim]")
        return

    # Convert models to dicts (mode="json" serializes enums to values)
    rows: List[Dict] = []
    for item in data:
        if isinstance(item, BaseModel):
            rows.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"value": item})

    if not rows:
        console.print("[dim]No data[/dim]")
        return

    # Auto-discover columns if not provided
    if columns is None:
        all_keys: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in all_keys:
                    all_keys.append(key)
        columns = all_keys

    if not columns:
        console.print("[dim]No data[/dim]")
        return

    # Limit columns for readability
    max_columns = 6
    if len(columns) > max_columns:
        columns = columns[:max_columns]

    # Use column names as headers if not provided
    if headers is None:
        headers = columns
    elif len(headers) > max_columns:
        headers = headers[:max_columns]

    # Create Rich table with box-drawing characters
    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        box=box.HEAVY_HEAD,
    )

    # Add columns - allow wrapping for long values
    for header, col in zip(headers, columns):
        table.add_column(header, no_wrap=False)

    # Add rows
    for row in rows:
        row_values = []
        for col in columns:
            value = row.get(col, "")
            row_values.append(_format_cell_value(value))
        table.add_row(*row_values)

    console.print(table)


def _serialize_for_json(obj: Any) -> Any:
    """Recursively serialize objects for JSON output, handling Pydantic models."""
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    elif hasattr(obj, 'model_dump'):
        # Pydantic v2 model not caught by isinstance
        return obj.model_dump()
    elif hasattr(obj, 'dict') and not isinstance(obj, dict):
        # Pydantic v1 model
        return obj.dict()
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif hasattr(obj, 'value'):
        # Enum
        return obj.value
    return obj


def print_json(data: Any, indent: int = 2, exclude_none: bool = False):
    """Print data as JSON to stdout.

    Handles Pydantic models (including nested), dicts, lists, and enums.
    Uses recursive serialization to handle deeply nested structures.

    Args:
        data: Data to print (model, dict, list of models/dicts)
        indent: JSON indentation level
        exclude_none: If True, omit None values from output (only for top-level models).
    """
    if isinstance(data, BaseModel) and exclude_none:
        output = data.model_dump(exclude_none=True)
    else:
        output = _serialize_for_json(data)

    print(json.dumps(output, indent=indent, ensure_ascii=False, default=str))


def print_output(data: Any, table: bool = False, indent: int = 2):
    """
    Print data in the specified format (JSON or table).

    Args:
        data: Data to output
        table: If True, output as table; otherwise as JSON
        indent: JSON indentation level (only used for JSON output)
    """
    if table:
        print_table(data)
    else:
        print_json(data, indent)


def print_error(message: str):
    """Print error message to stderr."""
    print(f"Error: {message}", file=sys.stderr)


def print_warning(message: str):
    """Print warning message to stderr (yellow)."""
    yellow = "\033[93m"
    reset = "\033[0m"
    print(f"{yellow}Warning: {message}{reset}", file=sys.stderr)


def print_success(message: str):
    """Print success message to stderr."""
    print(f"✓ {message}", file=sys.stderr)


def print_info(message: str):
    """Print informational message to stderr."""
    print(message, file=sys.stderr)


def handle_error(error: Exception) -> int:
    """Handle errors and return appropriate exit code."""
    from .client import ClientError
    if isinstance(error, ClientError):
        print_error(str(error))
        # Return 2 for credential errors, 1 for others
        if "credential" in str(error).lower() or "missing" in str(error).lower():
            return 2
        return 1
    print_error(str(error))
    return 1
