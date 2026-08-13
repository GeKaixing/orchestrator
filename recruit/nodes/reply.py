"""小店官方 IM 自动回复节点 (stage=reply).

扫描已招商房间: 达人新消息 -> rag 作答 -> im-chat 回复, 按 msgId 去重
(去重集合持久化在 darens.replied_msg_ids, 由 SQLite 写穿).

房间并行处理 (ThreadPoolExecutor): rag 为 HTTP 可并行; im_chat 由 shop worker 串行化.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import get_logger
from ..agents import client
from ..agents.retry import retry_result
from ..paths import CONTACTS_FILE
from ..state import RecruitState
from ..services import db, store

log = get_logger("reply")


def _process_room(cfg, r: dict, my_appid: str) -> dict | None:
    room_id, nick = r["roomId"], r["nickname"]
    key = r["wxid"]

    msgs_res = client.call("shop", "im_messages", room_id=room_id)
    if not msgs_res["success"]:
        log.warning("%s: 读消息失败/无消息", nick)
        return None
    msgs = msgs_res["data"].get("messages") or []

    entry = db.get_daren(key) or {}
    replied = set(entry.get("replied_msg_ids") or [])
    new_msgs = [m for m in msgs
                if m.get("sender") and m["sender"] != my_appid
                and m.get("msgId") and m["msgId"] not in replied
                and (m.get("content") or "").strip()]
    if not new_msgs:
        log.info("%s: 无新消息 (%d 条历史)", nick, len(msgs))
        return None

    replied_count = 0
    for m in new_msgs:
        content = m["content"].strip()
        log.info("%s: 达人消息: %s", nick, content[:60])
        tid = client.call("rag", "get_thread", key=room_id)["data"].get("thread_id")
        ask_res = client.call("rag", "ask", question=content, thread_id=tid)
        if not ask_res["success"]:
            log.error("%s: rag 失败: %s", nick, ask_res["error"])
            continue
        data = ask_res["data"]
        client.call("rag", "set_thread", key=room_id, thread_id=data["thread_id"])
        reply_text = client.call("rag", "collapse_reply", text=data["reply"])["data"]["text"]
        im_res = retry_result(
            lambda: client.call("shop", "im_chat", room_id=room_id, message=reply_text),
            attempts=cfg.retry + 1, label=f"reply:{room_id}",
        )
        if im_res["success"]:
            replied.add(m["msgId"])
            replied_count += 1
            log.info("%s: rag 回复已发送 (%d 字)", nick, len(reply_text))
        else:
            log.error("%s: 回复发送失败: %s", nick, im_res["error"])

    db.upsert_daren(key, nickname=nick, room_id=room_id, stage="im_sent",
                    replied_msg_ids=sorted(replied),
                    updated=time.strftime("%Y-%m-%d %H:%M:%S"))
    log.info("%s: 本轮回复 %d 条新消息", nick, replied_count)
    return db.get_daren(key) or {}


def reply(state: RecruitState) -> dict:
    cfg = state["config"]
    path = Path(cfg.contacts) if cfg.contacts else CONTACTS_FILE
    rooms = store.load_rooms(path)
    if not rooms:
        return {"error": f"contacts 里没有可用 roomId: {path}"}

    my_appid_res = client.call("shop", "load_my_appid")
    if not my_appid_res["success"] or not (my_appid_res["data"].get("appid") or ""):
        return {"error": "读不到店铺 appid: ~/.wxshop/api_config.json"}
    my_appid = my_appid_res["data"]["appid"]

    avail_res = client.call("rag", "available")
    if not avail_res["success"] or not avail_res["data"].get("available"):
        return {"error": "rag 服务不可用 (localhost:2024), 无法自动回复"}

    results: dict = {}
    workers = min(8, len(rooms) or 1)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        entries = list(ex.map(lambda r: _process_room(cfg, r, my_appid), rooms))
    for r, e in zip(rooms, entries):
        if e:
            results[r["wxid"]] = e

    log.info("本轮回复 %d 个房间", len(results))
    return {"rooms": rooms, "todo": rooms, "results": results}
