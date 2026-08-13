"""WeChat Agent — 包 recruit.services.wechat, 统一 run(action, **params)."""

from __future__ import annotations

from typing import Any

from .. import get_logger
from ..services import wechat
from .base import AgentResult, BaseAgent, fail, ok

log = get_logger("agents.wechat")


class WeChatAgent(BaseAgent):
    name = "wechat"

    def health(self) -> dict:
        try:
            if wechat.check_wechat():
                return {"ok": True, "detail": "微信桌面端运行中"}
            return {"ok": False, "detail": "微信桌面端未运行"}
        except Exception as e:  # noqa: BLE001
            log.error("wechat health 异常: %s", e)
            return {"ok": False, "detail": f"health 异常: {e}"}

    def run(self, action: str, **params: Any) -> AgentResult:
        if action == "add_friend":
            ok_b, reason = wechat.add_friend(params["wxid"])
            return ok({"wxid": params["wxid"]}) if ok_b else fail(reason)
        if action == "send_message":
            ok_b, reason = wechat.send_message(params["wxid"], params["text"])
            return ok({"wxid": params["wxid"]}) if ok_b else fail(reason)
        if action == "check_rag":
            return ok({"available": wechat.check_rag()}) if wechat.check_rag() \
                else fail("rag 服务不可用 (localhost:2024)")
        return fail(f"未知动作: {action}")


agent = WeChatAgent()
