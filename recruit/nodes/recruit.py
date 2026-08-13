"""每联系人子图: add → (成功且需 send) → send → done; 失败则直接 done."""

from __future__ import annotations

from .. import get_logger
from ..state import ContactState
from ..services import store, wechat

log = get_logger("recruit")


def add(state: ContactState) -> dict:
    if "add" not in state["actions"]:
        return {}
    contact, wxid = state["contact"], state["contact"]["wxid"]
    if store.load_state().get(wxid, {}).get("stage") == "added":
        log.info("已加好友, 跳过 add: %s", wxid)
        return {}
    ok, reason = wechat.add_friend(wxid)
    if ok:
        log.info("加好友成功: %s", wxid)
        return {"result": store.save_mark(contact, "added")}
    log.error("加好友失败: %s", reason)
    return {"result": store.save_mark(contact, "failed", reason)}


def route_after_add(state: ContactState) -> str:
    if "send" not in state["actions"]:
        return "done"
    result = state.get("result")
    # result 为空(已加好友跳过)或为 added → 继续发消息; 加好友失败 → 结束
    if result is None or result.get("stage") == "added":
        return "send"
    return "done"


def send(state: ContactState) -> dict:
    contact, wxid = state["contact"], state["contact"]["wxid"]
    ok, reason = wechat.send_message(wxid, state["text"])
    if ok:
        log.info("招商消息已发送: %s", wxid)
        return {"result": store.save_mark(contact, "sent")}
    # 发送失败不降级已完成的阶段 (保持 added/pending), 只记 reason
    prev = store.load_state().get(wxid, {}).get("stage", "pending")
    log.error("发送失败: %s", reason)
    return {"result": store.save_mark(contact, prev, reason)}


def done(state: ContactState) -> dict:
    contact = state["contact"]
    result = state.get("result") or store.load_state().get(contact["wxid"], {})
    return {"results": {contact["wxid"]: result}}
