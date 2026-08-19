"""子进程执行封装 — 复用原脚本 _run / _venv_python 的行为."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .. import get_logger
from .. import platform
from ..paths import WECHAT_SCRIPTS_DIR

log = get_logger("runner")


def _run(
    cmd: list[str],
    cwd: Path,
    timeout: int = 600,
    label: str = "",
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess | None:
    """执行外部命令并逐行记日志; 返回 CompletedProcess 或 None(超时/异常)."""
    log.info("RUN [%s] %s (cwd=%s)", label, " ".join(cmd), cwd)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        log.error("[%s] 执行超时 (%ds)", label, timeout)
        return None
    except Exception as e:  # noqa: BLE001
        log.error("[%s] 执行异常: %s", label, e)
        return None
    for line in (proc.stdout or "").splitlines():
        log.info("  [%s out] %s", label, line)
    for line in (proc.stderr or "").splitlines():
        log.info("  [%s err] %s", label, line)
    log.info("[%s] 退出码 %s", label, proc.returncode)
    return proc


def _venv_python(project_dir: Path) -> str | None:
    """Windows: .venv/Scripts/python.exe; Unix: .venv/bin/python"""
    return platform.venv_python(project_dir)


def wechat_scripts_on_path() -> None:
    """把 wechat-friend-add/scripts 加进 sys.path (幂等), 供惰性 import wechat_core."""
    if str(WECHAT_SCRIPTS_DIR) not in os.sys.path:
        os.sys.path.insert(0, str(WECHAT_SCRIPTS_DIR))
