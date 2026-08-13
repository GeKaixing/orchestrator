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
    """微信桌面端是否已打开并登录.

    进程在跑 ≠ 已登录: 登录后主窗口标题为「微信」(微信 4.x)。仅进程存在但
    无「微信」主窗口 → 视为未登录, 提醒用户打开并扫码登录。
    """
    try:
        core = _wechat_core()
        pid = core.get_wechat_pid()
        if not pid:
            log.error("微信桌面端未运行, 请先打开并登录微信")
            return False
        try:
            win = core.find_window(pid, "微信", exact=True)
        except Exception:  # noqa: BLE001
            win = None
        if win:
            log.info("微信已打开并登录 pid=%s", pid)
            return True
        log.error("微信进程在运行但未检测到「微信」主窗口, 请确认已扫码登录微信")
        return False
    except Exception as e:  # noqa: BLE001
        log.error("微信自检异常: %s", e)
    return False


def _parse_add_friend_reason(text: str) -> str:
    """从 add_friend.py 输出解析失败原因 (需求9: 注销/频繁/隐私等)."""
    text = text or ""
    for kw, reason in (
        ("微信未运行", "微信未运行, 请先打开并登录微信"),
        ("已经是好友", "已是好友 (幂等成功)"),
        ("无需重复添加", "已是好友"),
        ("操作频繁", "添加频繁, 触发风控"),
        ("频繁", "添加频繁, 触发风控"),
        ("未检测到", "添加失败: 对方设置隐私/已注销/已是好友"),
        ("申请添加朋友", "添加失败: 未弹出申请弹窗"),
        ("打开添加朋友弹窗失败", "打开添加朋友弹窗失败"),
    ):
        if kw in text:
            return reason
    return "add_friend 失败 (详情见日志)"


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
    # 失败: 从输出解析具体原因 (需求9: 频繁/隐私/未登录等), 供跟进表标记
    reason = _parse_add_friend_reason((proc.stdout or "") + (proc.stderr or "")) if proc else "执行异常"
    return False, reason


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
