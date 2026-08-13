"""微信桌面端动作封装 — 惰性导入 wechat_core / rag_client, 避免 import 期耦合."""

from __future__ import annotations

from pathlib import Path

from .. import get_logger
from ..paths import WECHAT_FRIEND_DIR, WECHAT_SCRIPTS_DIR
from .runner import _run, _venv_python, wechat_scripts_on_path

log = get_logger("wechat")


def _wechat_core():
    """导入并返回 wechat_core (来自 wechat-friend-add/scripts)."""
    wechat_scripts_on_path()
    import wechat_core  # type: ignore  # noqa: F401
    return wechat_core


def check_wechat() -> bool:
    try:
        core = _wechat_core()
        pid = core.get_wechat_pid()
        if pid:
            log.info("微信桌面端运行中 pid=%s", pid)
            return True
    except Exception as e:  # noqa: BLE001
        log.error("微信自检异常: %s", e)
    log.error("微信桌面端未运行, 请先打开并登录微信")
    return False


def check_rag() -> bool:
    try:
        wechat_scripts_on_path()
        import rag_client  # type: ignore
        if rag_client.available():
            log.info("rag 服务可用")
            return True
    except Exception as e:  # noqa: BLE001
        log.error("rag 自检异常: %s", e)
    log.error("rag 服务不可用 (localhost:2024), 自动回复需要它; 仅发固定文案可忽略")
    return False


def add_friend(wxid: str) -> tuple[bool, str]:
    py = _venv_python(WECHAT_FRIEND_DIR)
    if not py:
        log.error("找不到 wechat-friend-add 的 venv: %s", WECHAT_FRIEND_DIR)
        return False, "找不到 wechat-friend-add venv"
    proc = _run([py, "scripts/add_friend.py", "--wxid", wxid],
                WECHAT_FRIEND_DIR, timeout=180, label=f"add:{wxid}")
    if proc is not None and proc.returncode == 0:
        return True, ""
    return False, f"add_friend 退出码 {proc.returncode if proc else '异常'}"


def send_message(wxid: str, text: str) -> tuple[bool, str]:
    py = _venv_python(WECHAT_FRIEND_DIR)
    if not py:
        log.error("找不到 wechat-friend-add 的 venv: %s", WECHAT_FRIEND_DIR)
        return False, "找不到 wechat-friend-add venv"
    proc = _run([py, "scripts/send_message.py", "--wxid", wxid, "--text", text],
                WECHAT_FRIEND_DIR, timeout=300, label=f"send:{wxid}")
    if proc is not None and proc.returncode == 0:
        return True, ""
    return False, f"send_message 退出码 {proc.returncode if proc else '异常'}"
