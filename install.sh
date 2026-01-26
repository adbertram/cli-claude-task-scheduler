#!/bin/bash
# Install script for claude-task-scheduler CLI
# Run this script to set up the CLI for the current user

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_NAME="claude-task-scheduler"

echo "Installing $CLI_NAME CLI..."

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi

# Activate venv and install
echo "Installing package..."
source "$SCRIPT_DIR/.venv/bin/activate"

# Upgrade pip first (old versions don't support pyproject.toml editable installs)
pip3 install --upgrade pip --quiet

pip3 install -e "$SCRIPT_DIR" --quiet

# Ensure ~/.local/bin exists
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

# Create symlink
SYMLINK_PATH="$LOCAL_BIN/$CLI_NAME"
VENV_BIN="$SCRIPT_DIR/.venv/bin/$CLI_NAME"

if [ -L "$SYMLINK_PATH" ]; then
    rm "$SYMLINK_PATH"
fi

if [ -e "$SYMLINK_PATH" ]; then
    echo "Warning: $SYMLINK_PATH exists and is not a symlink. Skipping."
else
    ln -s "$VENV_BIN" "$SYMLINK_PATH"
    echo "Created symlink: $SYMLINK_PATH -> $VENV_BIN"
fi

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo ""
    echo "WARNING: $LOCAL_BIN is not in your PATH"
    echo "Add this to your ~/.zshrc or ~/.bashrc:"
    echo ""
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# Install Playwright browsers (for browser-based CLIs)
if [ -f "$SCRIPT_DIR/${CLI_NAME}_cli/browser.py" ]; then
    echo "Installing Playwright browsers..."
    "$SCRIPT_DIR/.venv/bin/playwright" install chromium
fi

echo ""
echo "Installation complete!"
echo ""

# Verify
if command -v $CLI_NAME &> /dev/null; then
    echo "Verified: $($CLI_NAME --version)"
else
    echo "Run 'hash -r' or open a new terminal, then try: $CLI_NAME --version"
fi
