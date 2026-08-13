"""前置自检节点."""

from __future__ import annotations

from .. import get_logger
from ..state import RecruitState
from ..services import wechat, wxshop

log = get_logger("preflight")


def preflight(state: RecruitState) -> dict:
    cfg = state["config"]
    if cfg.stage in ("all", "scan", "im") and not wxshop.check_login():
        return {"error": "wxshop 登录态失效, 请先扫码: cd wxshop-cli && .venv/Scripts/python -m wxshop login"}
    if cfg.stage in ("all", "add", "send") and not wechat.check_wechat():
        return {"error": "微信桌面端未运行, 请先打开并登录微信"}
    if cfg.stage in ("all", "send") and cfg.watch:
        wechat.check_rag()
    log.info("前置自检通过")
    return {"error": None}
