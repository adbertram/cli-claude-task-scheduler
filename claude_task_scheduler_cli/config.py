"""Configuration management for ClaudeTaskScheduler CLI."""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv, set_key


class Config:
    """Configuration manager for ClaudeTaskScheduler CLI authentication and settings."""

    def __init__(self):
        """Initialize configuration by loading from .env file."""
        # Use resolve() to get absolute path - ensures .env is found regardless of cwd
        config_dir = Path(__file__).resolve().parent.parent
        cli_env_path = config_dir / ".env"

        self.env_file_path = cli_env_path

        if cli_env_path.exists():
            load_dotenv(cli_env_path, override=True)
        else:
            # Create default .env if it doesn't exist
            cli_env_path.parent.mkdir(parents=True, exist_ok=True)
            cli_env_path.touch()

    @property
    def api_key(self) -> Optional[str]:
        """Get ClaudeTaskScheduler API key."""
        return os.getenv("CLAUDE_TASK_SCHEDULER_API_KEY")

    @property
    def client_id(self) -> Optional[str]:
        """Get ClaudeTaskScheduler OAuth client ID."""
        return os.getenv("CLAUDE_TASK_SCHEDULER_CLIENT_ID")

    @property
    def client_secret(self) -> Optional[str]:
        """Get ClaudeTaskScheduler OAuth client secret."""
        return os.getenv("CLAUDE_TASK_SCHEDULER_CLIENT_SECRET")

    @property
    def access_token(self) -> Optional[str]:
        """Get ClaudeTaskScheduler access token."""
        return os.getenv("CLAUDE_TASK_SCHEDULER_ACCESS_TOKEN")

    @property
    def refresh_token(self) -> Optional[str]:
        """Get ClaudeTaskScheduler refresh token."""
        return os.getenv("CLAUDE_TASK_SCHEDULER_REFRESH_TOKEN")

    @property
    def token_expires_at(self) -> Optional[str]:
        """Get token expiration timestamp."""
        return os.getenv("CLAUDE_TASK_SCHEDULER_TOKEN_EXPIRES_AT")

    @property
    def base_url(self) -> str:
        """Get ClaudeTaskScheduler API base URL."""
        return os.getenv("CLAUDE_TASK_SCHEDULER_BASE_URL", "local://scheduler")

    def has_credentials(self) -> bool:
        """Check if required credentials are available."""
        # Modify this based on your auth type (API key vs OAuth)
        return bool(self.api_key or self.access_token)

    def get_missing_credentials(self) -> list[str]:
        """Get list of missing credentials."""
        missing = []
        # Modify based on required credentials
        if not self.api_key and not self.access_token:
            missing.append("CLAUDE_TASK_SCHEDULER_API_KEY or CLAUDE_TASK_SCHEDULER_ACCESS_TOKEN")
        return missing

    def save_tokens(self, access_token: str, refresh_token: str, expires_at: str):
        """Save OAuth tokens to .env file and update environment."""
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_ACCESS_TOKEN", access_token)
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_REFRESH_TOKEN", refresh_token)
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_TOKEN_EXPIRES_AT", expires_at)
        # Also update os.environ so subsequent reads get the new values
        os.environ["CLAUDE_TASK_SCHEDULER_ACCESS_TOKEN"] = access_token
        os.environ["CLAUDE_TASK_SCHEDULER_REFRESH_TOKEN"] = refresh_token
        os.environ["CLAUDE_TASK_SCHEDULER_TOKEN_EXPIRES_AT"] = expires_at

    def save_api_key(self, api_key: str):
        """Save API key to .env file and update environment."""
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_API_KEY", api_key)
        os.environ["CLAUDE_TASK_SCHEDULER_API_KEY"] = api_key

    def clear_credentials(self):
        """Clear all credentials from .env file and environment."""
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_API_KEY", "")
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_ACCESS_TOKEN", "")
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_REFRESH_TOKEN", "")
        set_key(str(self.env_file_path), "CLAUDE_TASK_SCHEDULER_TOKEN_EXPIRES_AT", "")
        # Also clear from os.environ
        os.environ.pop("CLAUDE_TASK_SCHEDULER_API_KEY", None)
        os.environ.pop("CLAUDE_TASK_SCHEDULER_ACCESS_TOKEN", None)
        os.environ.pop("CLAUDE_TASK_SCHEDULER_REFRESH_TOKEN", None)
        os.environ.pop("CLAUDE_TASK_SCHEDULER_TOKEN_EXPIRES_AT", None)


# Global config instance - singleton pattern
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
