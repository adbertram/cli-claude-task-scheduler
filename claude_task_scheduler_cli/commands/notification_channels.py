"""Notification channel management commands."""

from typing import Optional

import typer

from ..db_client import DatabaseClient
from ..output import print_error, print_json, print_success, print_table

app = typer.Typer(help="Manage notification channels", no_args_is_help=True)


def _get_db_client() -> DatabaseClient:
    """Get database client."""
    return DatabaseClient()


# Slack channel commands
slack_app = typer.Typer(help="Manage Slack notification channels", no_args_is_help=True)
app.add_typer(slack_app, name="slack")


@slack_app.command("list")
def list_slack_channels(
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """List all Slack notification channels."""
    db_client = _get_db_client()

    channels = db_client.list_slack_channels()

    if table:
        print_table(
            channels,
            ["id", "channel_name", "enabled", "workspace_id", "delivery.method", "delivery.user_id"],
            ["ID", "Name", "Enabled", "Workspace", "Method", "User ID"],
        )
    else:
        print_json(channels)


@slack_app.command("get")
def get_slack_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Get a Slack notification channel by ID."""
    db_client = _get_db_client()

    channel = db_client.get_slack_channel(channel_id)
    if not channel:
        print_error(f"Slack channel not found: {channel_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [channel],
            ["id", "channel_name", "enabled", "workspace_id"],
            ["ID", "Name", "Enabled", "Workspace"],
        )
    else:
        print_json(channel)


@slack_app.command("update")
def update_slack_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    channel_name: Optional[str] = typer.Option(None, "--name", "-n", help="Channel name"),
    workspace_id: Optional[str] = typer.Option(None, "--workspace-id", "-w", help="Slack workspace ID"),
    delivery_method: Optional[str] = typer.Option(None, "--method", "-m", help="Delivery method"),
    delivery_channel_id: Optional[str] = typer.Option(None, "--channel-id", "-c", help="Slack channel ID"),
    delivery_user_id: Optional[str] = typer.Option(None, "--user-id", "-u", help="Slack user ID"),
    enabled: Optional[bool] = typer.Option(None, "--enabled/--disabled", help="Enable/disable channel"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Update a Slack notification channel."""
    db_client = _get_db_client()

    channel = db_client.update_slack_channel(
        channel_id,
        channel_name=channel_name,
        enabled=enabled,
        workspace_id=workspace_id,
        delivery_method=delivery_method,
        delivery_channel_id=delivery_channel_id,
        delivery_user_id=delivery_user_id,
    )

    if not channel:
        print_error(f"Slack channel not found: {channel_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [channel],
            ["id", "channel_name", "enabled", "workspace_id"],
            ["ID", "Name", "Enabled", "Workspace"],
        )
    else:
        print_json(channel)

    print_success(f"Slack channel '{channel.channel_name}' updated")


@slack_app.command("delete")
def delete_slack_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    force: bool = typer.Option(False, "--force", "-F", help="Skip confirmation"),
):
    """Delete a Slack notification channel."""
    db_client = _get_db_client()

    channel = db_client.get_slack_channel(channel_id)
    if not channel:
        print_error(f"Slack channel not found: {channel_id}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete Slack channel '{channel.channel_name}'?")
        if not confirm:
            raise typer.Abort()

    db_client.delete_slack_channel(channel_id)
    print_success(f"Slack channel '{channel.channel_name}' deleted")


# Gmail channel commands
gmail_app = typer.Typer(help="Manage Gmail notification channels", no_args_is_help=True)
app.add_typer(gmail_app, name="gmail")


@gmail_app.command("list")
def list_gmail_channels(
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """List all Gmail notification channels."""
    db_client = _get_db_client()

    channels = db_client.list_gmail_channels()

    if table:
        print_table(
            channels,
            ["id", "channel_name", "enabled", "email_address"],
            ["ID", "Name", "Enabled", "Email"],
        )
    else:
        print_json(channels)


@gmail_app.command("get")
def get_gmail_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Get a Gmail notification channel by ID."""
    db_client = _get_db_client()

    channel = db_client.get_gmail_channel(channel_id)
    if not channel:
        print_error(f"Gmail channel not found: {channel_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [channel],
            ["id", "channel_name", "enabled", "email_address"],
            ["ID", "Name", "Enabled", "Email"],
        )
    else:
        print_json(channel)


@gmail_app.command("update")
def update_gmail_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    channel_name: Optional[str] = typer.Option(None, "--name", "-n", help="Channel name"),
    email_address: Optional[str] = typer.Option(None, "--email", "-e", help="Email address"),
    enabled: Optional[bool] = typer.Option(None, "--enabled/--disabled", help="Enable/disable channel"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Update a Gmail notification channel."""
    db_client = _get_db_client()

    channel = db_client.update_gmail_channel(
        channel_id,
        channel_name=channel_name,
        enabled=enabled,
        email_address=email_address,
    )

    if not channel:
        print_error(f"Gmail channel not found: {channel_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [channel],
            ["id", "channel_name", "enabled", "email_address"],
            ["ID", "Name", "Enabled", "Email"],
        )
    else:
        print_json(channel)

    print_success(f"Gmail channel '{channel.channel_name}' updated")


@gmail_app.command("delete")
def delete_gmail_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    force: bool = typer.Option(False, "--force", "-F", help="Skip confirmation"),
):
    """Delete a Gmail notification channel."""
    db_client = _get_db_client()

    channel = db_client.get_gmail_channel(channel_id)
    if not channel:
        print_error(f"Gmail channel not found: {channel_id}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete Gmail channel '{channel.channel_name}'?")
        if not confirm:
            raise typer.Abort()

    db_client.delete_gmail_channel(channel_id)
    print_success(f"Gmail channel '{channel.channel_name}' deleted")


# Macos channel commands
macos_app = typer.Typer(help="Manage macOS desktop notification channels", no_args_is_help=True)
app.add_typer(macos_app, name="macos")


@macos_app.command("list")
def list_macos_channels(
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """List all macOS desktop notification channels."""
    db_client = _get_db_client()

    channels = db_client.list_macos_channels()

    if table:
        print_table(
            channels,
            ["id", "channel_name", "enabled", "sound", "ignore_dnd"],
            ["ID", "Name", "Enabled", "Sound", "Ignore DND"],
        )
    else:
        print_json(channels)


@macos_app.command("get")
def get_macos_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Get a macOS desktop notification channel by ID."""
    db_client = _get_db_client()

    channel = db_client.get_macos_channel(channel_id)
    if not channel:
        print_error(f"Macos channel not found: {channel_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [channel],
            ["id", "channel_name", "enabled", "sound", "ignore_dnd"],
            ["ID", "Name", "Enabled", "Sound", "Ignore DND"],
        )
    else:
        print_json(channel)


@macos_app.command("update")
def update_macos_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    channel_name: Optional[str] = typer.Option(None, "--name", "-n", help="Channel name"),
    sound: Optional[str] = typer.Option(None, "--sound", "-s", help="Sound to play"),
    ignore_dnd: Optional[bool] = typer.Option(None, "--ignore-dnd/--no-ignore-dnd", help="Ignore Do Not Disturb"),
    enabled: Optional[bool] = typer.Option(None, "--enabled/--disabled", help="Enable/disable channel"),
    table: bool = typer.Option(False, "--table", help="Display as table"),
):
    """Update a macOS desktop notification channel."""
    db_client = _get_db_client()

    channel = db_client.update_macos_channel(
        channel_id,
        channel_name=channel_name,
        enabled=enabled,
        sound=sound,
        ignore_dnd=ignore_dnd,
    )

    if not channel:
        print_error(f"Macos channel not found: {channel_id}")
        raise typer.Exit(1)

    if table:
        print_table(
            [channel],
            ["id", "channel_name", "enabled", "sound", "ignore_dnd"],
            ["ID", "Name", "Enabled", "Sound", "Ignore DND"],
        )
    else:
        print_json(channel)

    print_success(f"Macos channel '{channel.channel_name}' updated")


@macos_app.command("delete")
def delete_macos_channel(
    channel_id: str = typer.Argument(..., help="Channel ID"),
    force: bool = typer.Option(False, "--force", "-F", help="Skip confirmation"),
):
    """Delete a macOS desktop notification channel."""
    db_client = _get_db_client()

    channel = db_client.get_macos_channel(channel_id)
    if not channel:
        print_error(f"Macos channel not found: {channel_id}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete Macos channel '{channel.channel_name}'?")
        if not confirm:
            raise typer.Abort()

    db_client.delete_macos_channel(channel_id)
    print_success(f"Macos channel '{channel.channel_name}' deleted")
