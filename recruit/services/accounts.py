"""小店账号池管理 — 满足「多账号轮换」需求.

wxshop-cli 登录态: default 在 .wxshop/weixin_store_state.json, 具名账号在
.wxshop/accounts/<name>/weixin_store_state.json (见 wxshop cli.py _paths_for).

orchestrator 侧:
  - list_accounts(): 扫文件系统列出全部账号 (default + accounts/*).
  - check_login(account): wxshop persist verify 解析 verdict, 判定登录是否真有效.
  - current()/set_current(): 当前选中账号, 持久化在 settings 表 (需求2: 下次循环沿用).
  - next_available(): 遍历账号返回第一个登录有效的; 全无效 → 返回 None + 原因
    (提示添加新账号 / 24 点后次数恢复).
  - login_env(account): 注入 WXSHOP_ACCOUNT 环境变量, 供 wxshop 子进程选账号.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .. import get_logger
from .. import paths
from . import db
from .runner import _run, _venv_python

log = get_logger("accounts")

_SETTING_KEY = "current_wxshop_account"


def _wxshop_py() -> str | None:
    return _venv_python(paths.WXSHOP_DIR)


def _account_state_path(account: str) -> Path:
    """某账号的登录态文件路径."""
    if account == "default":
        return paths.WXSHOP_STATE_DIR / "weixin_store_state.json"
    return paths.WXSHOP_STATE_DIR / "accounts" / account / "weixin_store_state.json"


def _account_api_path(account: str) -> Path:
    if account == "default":
        return paths.WXSHOP_STATE_DIR / "api_config.json"
    return paths.WXSHOP_STATE_DIR / "accounts" / account / "api_config.json"


def _account_meta_path(account: str) -> Path:
    if account == "default":
        return paths.WXSHOP_STATE_DIR / "account.json"
    return paths.WXSHOP_STATE_DIR / "accounts" / account / "account.json"


def list_accounts() -> list[str]:
    """全部账号名: 恒含 default, 其余扫 .wxshop/accounts/* (与 wxshop _list_accounts 一致)."""
    names = ["default"]
    base = paths.WXSHOP_STATE_DIR / "accounts"
    if base.is_dir():
        for n in sorted(os.listdir(base)):
            p = base / n
            if p.is_dir() and (p / "weixin_store_state.json").exists():
                names.append(n)
    # 只有真正有登录态文件的账号才算数
    return [n for n in names if _account_state_path(n).exists()] or ["default"]


def account_nickname(account: str) -> str:
    """从 account.json 读店铺昵称, 供展示/提示."""
    try:
        meta = json.loads(_account_meta_path(account).read_text(encoding="utf-8"))
        return meta.get("nickname") or account
    except Exception:  # noqa: BLE001
        return account


def login_env(account: str) -> dict[str, str]:
    """给 wxshop 子进程注入选账号的环境变量."""
    return {"WXSHOP_ACCOUNT": account}


def check_login(account: str, timeout: int = 120) -> dict:
    """判定某账号登录是否真有效 (解析 persist verify 的 verdict, 非只看退出码)."""
    py = _wxshop_py()
    if not py:
        return {"ok": False, "detail": "找不到 wxshop venv"}
    proc = _run([py, "-m", "wxshop", "persist", "verify", "--account", account],
                paths.WXSHOP_DIR, timeout=timeout, label=f"persist:{account}",
                env_extra=login_env(account))
    if proc is None or proc.returncode != 0:
        return {"ok": False, "detail": f"persist verify 失败 (退出码 {proc.returncode if proc else '异常'})"}
    try:
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"ok": False, "detail": "persist verify 输出无法解析"}
    verdict = str(data.get("verdict") or "")
    ok = verdict.startswith("PASS") or bool(data.get("login") and data.get("stateExists"))
    return {
        "ok": ok,
        "detail": verdict or "未登录",
        "stateExists": bool(data.get("stateExists")),
        "login": bool(data.get("login")),
        "appid": (data.get("store") or {}).get("appid") or "",
        "nickname": (data.get("store") or {}).get("nickName") or "",
        "account": account,
    }


def appid(account: str) -> str:
    """读某账号店铺 appid, 用于识别对方(达人)消息.

    优先 account.json (login 时保存 nickname+appid), 兜底 api_config.json.
    """
    try:
        meta = json.loads(_account_meta_path(account).read_text(encoding="utf-8"))
        if meta.get("appid"):
            return meta["appid"]
    except Exception:  # noqa: BLE001
        pass
    try:
        cfg = json.loads(_account_api_path(account).read_text(encoding="utf-8"))
        return (cfg or {}).get("appid", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def current() -> str:
    """当前选中账号 (settings 持久化; 缺省 default 且登录有效)."""
    db.init_db()  # 确保 settings 表存在 (worker 进程首次读时)
    name = db.get_setting(_SETTING_KEY, "")
    if name and _account_state_path(name).exists():
        return name
    return "default"


def set_current(account: str) -> None:
    db.init_db()
    db.set_setting(_SETTING_KEY, account)
    log.info("当前小店账号 → %s", account)


def next_available() -> tuple[str | None, str | None]:
    """返回第一个「登录有效」的账号; 全部无效 → (None, 提示).

    轮换顺序: 当前账号优先, 其余按列表顺序 (需求2: 次数耗尽不再从无次数的开始).
    注意: 这里只验证登录有效性, 「是否有提取次数」在 scan 阶段由 dailyLimitHit 判定.
    """
    accounts = list_accounts()
    if not accounts:
        return None, "没有可用的小店账号, 请先 `wxshop login` 扫码"
    cur = current()
    ordered = ([cur] + [a for a in accounts if a != cur]) if cur in accounts else accounts
    failures: list[str] = []
    for acc in ordered:
        h = check_login(acc)
        if h["ok"]:
            log.info("选中小店账号: %s (%s)", acc, h.get("nickname") or acc)
            set_current(acc)
            return acc, None
        failures.append(f"{acc}({h.get('detail')})")
    return None, ("所有小店账号均未登录: " + "; ".join(failures)
                  + "。请添加新账号登录 (`wxshop login --account <名称>`), "
                    "或等 24 点后联系方式次数恢复再开始工作流")


def login_new(account: str) -> dict:
    """引导用户为新账号扫码登录 (wxshop login --account <name>).

    注: 扫码是交互式的, 这里只是构造命令提示, 由用户手动执行.
    """
    return {
        "cmd": f"cd {paths.WXSHOP_DIR} && uv run python -m wxshop login --account {account}",
        "hint": "登录成功后该账号登录态存入 .wxshop/accounts/<名称>/",
    }
