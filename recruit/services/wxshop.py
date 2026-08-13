"""wxshop-cli 命令封装 (扫描/提取/IM 招商)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .. import get_logger
from ..paths import WXSHOP_DIR
from . import accounts
from .runner import _run, _venv_python

log = get_logger("wxshop")


def _env(account: str | None = None) -> dict | None:
    """给 wxshop 子进程注入选账号的环境变量 (None 时用当前账号)."""
    acc = account or accounts.current()
    return accounts.login_env(acc)


def check_login(account: str | None = None) -> bool:
    """判定 wxshop 登录是否真有效 (解析 persist verify 的 verdict, 非只看退出码)."""
    acc = account or accounts.current()
    h = accounts.check_login(acc)
    if h["ok"]:
        log.info("wxshop 登录态有效 (账号 %s, %s)", acc, h.get("nickname") or "")
        return True
    log.error("wxshop 登录态失效 (%s), 请扫码: cd wxshop-cli && uv run python -m wxshop login --account %s",
              h.get("detail"), acc)
    return False


def scan(talents: Path, cat: str | None = None, max_pages: int = 1,
         account: str | None = None) -> bool:
    """--with-im: 逐条建 IM 房间输出 imUrl(含 roomId). 不加则 daren-contact 会全部 skipped."""
    py = _venv_python(WXSHOP_DIR)
    if not py:
        log.error("找不到 wxshop venv")
        return False
    cmd = [py, "-m", "wxshop", "daren-scan", "--contact", "--with-im",
           "--max-pages", str(max_pages), "--out", str(talents)]
    if cat:
        cmd += ["--cat", cat]
    proc = _run(cmd, WXSHOP_DIR, timeout=1800, label="scan", env_extra=_env(account))
    return proc is not None and proc.returncode == 0 and talents.exists()


def backfill_room_ids(talents: Path) -> int:
    """scan --with-im 只输出 imUrl(含 roomId), 把 roomId 回填到每行供 daren-contact 使用."""
    rows: list[dict] = []
    for line in talents.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if not (r.get("roomId") or r.get("room_id")):
            m = re.search(r"roomId=([^&]+)", r.get("imUrl") or "")
            if m:
                r["roomId"] = m.group(1)
        rows.append(r)
    talents.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                       encoding="utf-8")
    filled = sum(1 for r in rows if r.get("roomId") or r.get("room_id"))
    log.info("回填 roomId: %d/%d 行", filled, len(rows))
    return filled


def contact(talents: Path, contacts: Path, account: str | None = None) -> bool:
    py = _venv_python(WXSHOP_DIR)
    if not py:
        log.error("找不到 wxshop venv")
        return False
    proc = _run([py, "-m", "wxshop", "daren-contact", "--in", str(talents), "--out", str(contacts)],
                WXSHOP_DIR, timeout=1800, label="contact", env_extra=_env(account))
    return proc is not None and proc.returncode == 0 and contacts.exists()


def im_chat(room_id: str, message: str, account: str | None = None) -> tuple[bool, str]:
    """小店官方 IM 招商: im-send 的 API 已失效(404), 走 im-chat UI 路径.

    以 stdout 含 '"ok": true' 判定页面操作成功.
    """
    py = _venv_python(WXSHOP_DIR)
    if not py:
        return False, "找不到 wxshop venv"
    proc = _run([py, "-m", "wxshop", "im-chat", "--room-id", room_id, "--message", message],
                WXSHOP_DIR, timeout=120, label=f"im:{room_id}", env_extra=_env(account))
    if proc is not None and proc.returncode == 0 and '"ok": true' in (proc.stdout or ""):
        return True, ""
    return False, f"im-chat 退出码 {proc.returncode if proc else '异常'}"


def im_messages(room_id: str, account: str | None = None) -> list[dict] | None:
    """调 wxshop im-messages 读房间消息 (已过滤系统消息). 失败/无消息返回 None."""
    py = _venv_python(WXSHOP_DIR)
    if not py:
        return None
    proc = _run([py, "-m", "wxshop", "im-messages", "--room-id", room_id],
                WXSHOP_DIR, timeout=90, label=f"immsg:{room_id}", env_extra=_env(account))
    if proc is None or proc.returncode != 0:
        return None
    lines = (proc.stdout or "").strip().splitlines()
    if not lines:
        return None
    try:
        data = json.loads(lines[-1])
    except Exception:  # noqa: BLE001
        return None
    return data.get("messages") or []


def load_my_appid(account: str | None = None) -> str:
    """读当前/指定小店账号店铺 appid, 用于识别对方(达人)消息."""
    return accounts.appid(account or accounts.current())
