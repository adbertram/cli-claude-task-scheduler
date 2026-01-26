"""Authentication commands for ClaudeTaskScheduler CLI."""
import typer
from ..config import get_config
from ..output import print_json, print_table, print_success, print_error, print_info, handle_error

app = typer.Typer(help="Manage ClaudeTaskScheduler API authentication", no_args_is_help=True)


@app.command("login")
def auth_login(
    api_key: str = typer.Option(None, "--api-key", "-k", help="ClaudeTaskScheduler API key"),
    force: bool = typer.Option(False, "--force", "-F", help="Clear existing credentials and re-authenticate"),
):
    """
    Configure ClaudeTaskScheduler API authentication.

    Example:
        claude-task-scheduler auth login
        claude-task-scheduler auth login --api-key YOUR_API_KEY
        claude-task-scheduler auth login --force  # Clear existing and re-authenticate
    """
    try:
        config = get_config()

        # Clear existing credentials if --force is specified
        if force:
            config.clear_credentials()
            print_info("Existing credentials cleared")

        if not api_key:
            api_key = typer.prompt("Enter your ClaudeTaskScheduler API key", hide_input=True)

        if not api_key or not api_key.strip():
            print_error("API key cannot be empty")
            raise typer.Exit(1)

        config.save_api_key(api_key.strip())
        print_success("API key saved successfully")

    except typer.Exit:
        raise
    except Exception as e:
        raise typer.Exit(handle_error(e))


@app.command("logout")
def auth_logout():
    """Clear stored ClaudeTaskScheduler API credentials."""
    try:
        config = get_config()
        config.clear_credentials()
        print_success("Credentials cleared")
    except Exception as e:
        raise typer.Exit(handle_error(e))


@app.command("status")
def auth_status(
    table: bool = typer.Option(False, "--table", "-t", help="Display as table"),
):
    """Check ClaudeTaskScheduler API authentication status."""
    try:
        config = get_config()

        if config.has_credentials():
            # Mask credentials for display
            if config.api_key:
                key = config.api_key
                masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
            elif config.access_token:
                token = config.access_token
                masked = token[:10] + "..." + token[-4:] if len(token) > 14 else "***"
            else:
                masked = "***"

            status_data = {
                "authenticated": True,
                "credential": masked,
                "base_url": config.base_url,
            }

            if table:
                print_table(
                    [status_data],
                    ["authenticated", "credential", "base_url"],
                    ["Authenticated", "Credential", "Base URL"],
                )
            else:
                print_json(status_data)
            raise typer.Exit(0)
        else:
            status_data = {
                "authenticated": False,
                "message": "Not authenticated. Run 'claude-task-scheduler auth login' to configure.",
            }

            if table:
                print_table(
                    [status_data],
                    ["authenticated", "message"],
                    ["Authenticated", "Message"],
                )
            else:
                print_json(status_data)
            raise typer.Exit(2)

    except typer.Exit:
        raise
    except Exception as e:
        raise typer.Exit(handle_error(e))
