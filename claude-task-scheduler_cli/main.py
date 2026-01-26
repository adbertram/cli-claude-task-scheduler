"""Main entry point for ClaudeTaskScheduler CLI."""
import typer
from typing import Optional
from .client import ClientError

app = typer.Typer(
    name="claude-task-scheduler",
    help="CLI interface for ClaudeTaskScheduler API",
    add_completion=True,  # Enables --install-completion
)

# Register command modules
from .commands import auth, items
app.add_typer(auth.app, name="auth", help="Manage ClaudeTaskScheduler API authentication")
app.add_typer(items.app, name="items", help="Manage claude-task-scheduler items")


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show version and exit", is_eager=True
    ),
):
    """ClaudeTaskScheduler CLI - Manage ClaudeTaskScheduler from the command line."""
    if version:
        from . import __version__
        typer.echo(f"claude-task-scheduler-cli version {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main():
    """Main entry point."""
    try:
        app()
    except ClientError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2)
    except KeyboardInterrupt:
        typer.echo("\nAborted!", err=True)
        raise typer.Exit(130)


if __name__ == "__main__":
    main()
