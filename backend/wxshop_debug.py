"""wxshop CLI 调试通道 — 桌面端执行任意 wxshop 命令并回传 stdout/stderr.

命令白名单限制第一条参数, 防止误把任意程序当 wxshop 子命令跑.
"""

from __future__ import annotations

import os
import subprocess

from recruit.paths import WXSHOP_DIR

KNOWN_COMMANDS = frozenset({
    "doctor", "login", "home", "daren-list", "daren-scan", "daren-filters",
    "grade", "daren-detail", "daren-contact", "goods-list", "agency-list",
    "league-list", "order-list", "order-detail", "aftersale-list",
    "transaction-stats", "im-send", "im-chat", "im-messages", "coop-export",
    "coop-manage", "persist", "account", "config", "shop-info", "shop-link",
    "shop-taglink", "favorites", "compass", "explain",
})

MAX_OUT = 30_000  # 截断, 防超大输出撑爆内存/响应


def run(argv: list[str], timeout: int = 600) -> dict:
    if not argv or argv[0] not in KNOWN_COMMANDS:
        return {
            "ok": False,
            "error": f"未知命令: {argv[0] if argv else '(空)'}",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            ["uv", "run", "wxshop", *argv],
            cwd=str(WXSHOP_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "error": f"超时 ({timeout}s)",
            "exit_code": None,
            "stdout": (e.stdout or "")[-MAX_OUT:],
            "stderr": (e.stderr or "")[-MAX_OUT:],
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"启动失败: {e}", "exit_code": None,
                "stdout": "", "stderr": ""}
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "")[-MAX_OUT:],
        "stderr": (proc.stderr or "")[-MAX_OUT:],
    }
