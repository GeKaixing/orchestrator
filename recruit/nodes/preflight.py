"""前置自检节点 — 并行探测三个 agent 健康, 按 stage 判定依赖."""

from __future__ import annotations

from .. import get_logger
from ..agents import client
from ..state import RecruitState

log = get_logger("preflight")


def preflight(state: RecruitState) -> dict:
    cfg = state["config"]
    healths = client.health_all()
    shop_ok = healths.get("shop", {}).get("ok", False)
    wechat_ok = healths.get("wechat", {}).get("ok", False)
    rag_ok = healths.get("rag", {}).get("ok", False)

    if cfg.stage in ("all", "scan", "im", "invite", "reply") and not shop_ok:
        detail = healths.get("shop", {}).get("detail", "wxshop 不可用")
        return {"error": f"wxshop 登录态失效, 请先扫码: cd wxshop-cli && .venv/Scripts/python -m wxshop login ({detail})"}
    if cfg.stage in ("all", "add", "send", "invite") and not wechat_ok:
        detail = healths.get("wechat", {}).get("detail", "微信桌面端未运行")
        return {"error": f"微信桌面端未运行, 请先打开并登录微信 ({detail})"}
    if cfg.stage in ("all", "send") and cfg.watch:
        client.call("wechat", "check_rag")
    if cfg.stage == "reply" and not rag_ok:
        detail = healths.get("rag", {}).get("detail", "rag 不可用")
        return {"error": f"rag 服务不可用 (localhost:2024), 无法自动回复 ({detail})"}
    log.info("前置自检通过: shop=%s wechat=%s rag=%s", shop_ok, wechat_ok, rag_ok)
    return {"error": None}
