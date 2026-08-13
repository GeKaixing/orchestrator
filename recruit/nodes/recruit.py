"""每联系人子图: add → (成功且需 send) → send → done; 失败则直接 done.

动作经 Agent 客户端调用 (worker 优先, 回落直调), 失败按 config.retry 重试.
"""

from __future__ import annotations

from .. import get_logger
from ..agents import client
from ..agents.retry import retry_result
from ..state import ContactState
from ..services import store

log = get_logger("recruit")


def add(state: ContactState) -> dict:
    if "add" not in state["actions"]:
        return {}
    contact, wxid = state["contact"], state["contact"]["wxid"]
    if store.load_state().get(wxid, {}).get("stage") == "added":
        log.info("已加好友, 跳过 add: %s", wxid)
        return {}
    res = retry_result(
        lambda: client.call("wechat", "add_friend", wxid=wxid),
        attempts=state.get("retry", 1) + 1, label=f"add:{wxid}",
    )
    if res["success"]:
        log.info("加好友成功: %s", wxid)
        return {"result": store.save_mark(contact, "added")}
    reason = res["error"] or "add_friend 失败"
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
    res = retry_result(
        lambda: client.call("wechat", "send_message", wxid=wxid, text=state["text"]),
        attempts=state.get("retry", 1) + 1, label=f"send:{wxid}",
    )
    if res["success"]:
        log.info("招商消息已发送: %s", wxid)
        return {"result": store.save_mark(contact, "sent")}
    # 发送失败不降级已完成的阶段 (保持 added/pending), 只记 reason
    reason = res["error"] or "send_message 失败"
    prev = store.load_state().get(wxid, {}).get("stage", "pending")
    log.error("发送失败: %s", reason)
    return {"result": store.save_mark(contact, prev, reason)}


def done(state: ContactState) -> dict:
    contact = state["contact"]
    result = state.get("result") or store.load_state().get(contact["wxid"], {})
    return {"results": {contact["wxid"]: result}}
