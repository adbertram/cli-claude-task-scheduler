"""Health check utilities for daemon status detection via Unix socket."""

import json
import socket
from pathlib import Path
from typing import Optional


def get_socket_path() -> Path:
    """Get the Unix socket path for health checks."""
    return Path.home() / ".claude-task-scheduler" / "daemon.sock"


def get_pid_file_path() -> Path:
    """Get the PID file path for daemon management."""
    return Path.home() / ".claude-task-scheduler" / "daemon.pid"


def check_daemon_health() -> dict:
    """Check daemon health via Unix socket.

    Connects to the daemon's health endpoint and returns status information.

    Returns:
        Dict with health status:
        - If running: {"running": True, "uptime_seconds": ...}
        - If not running: {"running": False, "reason": "..."}
    """
    socket_path = get_socket_path()

    if not socket_path.exists():
        return {"running": False, "reason": "Socket file not found"}

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(str(socket_path))
        sock.sendall(b"GET /health HTTP/1.0\r\n\r\n")
        response = sock.recv(4096).decode()
        sock.close()

        # Parse HTTP response body
        if "\r\n\r\n" in response:
            body = response.split("\r\n\r\n", 1)[1]
        elif "\n\n" in response:
            body = response.split("\n\n", 1)[1]
        else:
            return {"running": False, "reason": "Invalid response format"}

        return json.loads(body)
    except ConnectionRefusedError:
        return {"running": False, "reason": "Connection refused - daemon may have stopped"}
    except socket.timeout:
        return {"running": False, "reason": "Connection timeout"}
    except json.JSONDecodeError as e:
        return {"running": False, "reason": f"Invalid JSON response: {e}"}
    except Exception as e:
        return {"running": False, "reason": str(e)}
