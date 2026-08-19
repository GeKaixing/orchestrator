"""Small cross-platform helpers for local desktop orchestration."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any


IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"

CREATE_NEW_PROCESS_GROUP = 0x00000200 if IS_WINDOWS else 0


def popen_kwargs() -> dict[str, Any]:
    """Return platform-specific kwargs for subprocesses that may need tree cleanup."""
    if IS_WINDOWS:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_process_tree(pid: int, timeout: int = 30) -> None:
    """Stop a process and its children where the platform gives us a simple primitive."""
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=timeout,
            )
        except Exception:  # noqa: BLE001
            pass
        return

    try:
        os.killpg(pid, signal.SIGTERM)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:  # noqa: BLE001
        pass


def resolve_executable(name: str) -> str | None:
    """Resolve executable names, including Windows npm/npx command shims."""
    if IS_WINDOWS and not name.lower().endswith((".exe", ".cmd", ".bat")):
        if name in {"npm", "npx"}:
            name = f"{name}.cmd"
    return shutil.which(name)


def venv_python(project_dir: Path) -> str | None:
    """Return the Python executable inside a project virtual environment."""
    for path in (
        project_dir / ".venv" / "Scripts" / "python.exe",
        project_dir / ".venv" / "bin" / "python",
    ):
        if path.exists():
            return str(path)
    return None


def platform_payload() -> dict[str, object]:
    """Return concise platform info for UI hints."""
    if IS_WINDOWS:
        return {
            "platform": "windows",
            "path_separator": "\\",
            "wechat_agent_dir": "agents\\wechat-friend-add",
            "wechat_setup_command": "powershell -ExecutionPolicy Bypass -File setup.ps1",
            "setup_command": "run_desktop.bat",
            "permissions": [],
        }
    if IS_MACOS:
        return {
            "platform": "macos",
            "path_separator": "/",
            "wechat_agent_dir": "agents/wechat-friend-add",
            "wechat_setup_command": "uv sync",
            "setup_command": "./run_desktop.sh",
            "permissions": ["辅助功能", "屏幕录制", "输入监控"],
        }
    return {
        "platform": sys.platform,
        "path_separator": "/",
        "wechat_agent_dir": "agents/wechat-friend-add",
        "wechat_setup_command": "uv sync",
        "setup_command": "./run_desktop.sh",
        "permissions": [],
    }
