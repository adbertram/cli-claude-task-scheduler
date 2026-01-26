"""Main entry point for Claude Task Scheduler CLI."""

from typing import Optional

import typer

app = typer.Typer(
    name="claude-task-scheduler",
    help="Schedule and execute Claude Code prompts with auto-resume, notifications, and logging",
    add_completion=True,
)

# Register command modules
from .commands import daemon, notification_channels, runs, tasks

app.add_typer(tasks.app, name="tasks", help="Manage scheduled tasks")
app.add_typer(runs.app, name="runs", help="Manage task runs")
app.add_typer(daemon.app, name="daemon", help="Manage scheduler daemon")
app.add_typer(notification_channels.app, name="channels", help="Manage notification channels")


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit", is_eager=True
    ),
):
    """Claude Task Scheduler - Schedule and execute Claude Code prompts."""
    if version:
        from . import __version__

        typer.echo(f"claude-task-scheduler version {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main():
    """Main entry point."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\nAborted!", err=True)
        raise typer.Exit(130)


if __name__ == "__main__":
    main()
