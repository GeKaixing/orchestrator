"""Shop Agent — 包 recruit.services.wxshop, 统一 run(action, **params)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import get_logger
from ..paths import CONTACTS_FILE, TALENTS_FILE
from ..services import wxshop
from .base import AgentResult, BaseAgent, fail, ok

log = get_logger("agents.shop")


class ShopAgent(BaseAgent):
    name = "shop"

    def health(self) -> dict:
        try:
            if wxshop.check_login():
                return {"ok": True, "detail": "wxshop 登录态有效"}
            return {"ok": False, "detail": "wxshop 登录态失效"}
        except Exception as e:  # noqa: BLE001
            log.error("shop health 异常: %s", e)
            return {"ok": False, "detail": f"health 异常: {e}"}

    def run(self, action: str, **params: Any) -> AgentResult:
        account = params.get("account")
        if action == "scan":
            out = Path(params.get("out") or TALENTS_FILE)
            ok_b = wxshop.scan(out, params.get("cat"), int(params.get("max_pages") or 1),
                               account=account)
            return ok({"out": str(out)}) if ok_b else fail("daren-scan 失败")
        if action == "backfill_room_ids":
            path = Path(params.get("path") or TALENTS_FILE)
            n = wxshop.backfill_room_ids(path)
            return ok({"filled": n})
        if action == "contact":
            in_path = Path(params.get("in_path") or TALENTS_FILE)
            out_path = Path(params.get("out_path") or CONTACTS_FILE)
            ok_b = wxshop.contact(in_path, out_path, account=account)
            return ok({"out": str(out_path)}) if ok_b else fail("daren-contact 失败")
        if action == "im_chat":
            ok_b, reason = wxshop.im_chat(params["room_id"], params["message"], account=account)
            return ok({"room_id": params["room_id"]}) if ok_b else fail(reason)
        if action == "im_messages":
            msgs = wxshop.im_messages(params["room_id"], account=account)
            if msgs is None:
                return fail("读消息失败/无消息")
            return ok({"messages": msgs})
        if action == "load_my_appid":
            return ok({"appid": wxshop.load_my_appid(account=account)})
        return fail(f"未知动作: {action}")


agent = ShopAgent()
