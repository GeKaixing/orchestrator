"""invite 阶段 (stage=invite): 小店 IM 固定文案邀约 → 有联系方式则微信加好友复邀.

IM 发送进度写穿 darens.im_msgs_sent, 中断后续发不重发.
用户约束 (2026-08-13): 加好友只加好友, 不发送招商文案 —
  文案不能在好友申请中发出, 等对方通过好友后再跟进 (reply 自动回复 / 手动 send_message)。
状态流转:
  IM 全成功 → 有 contact_wxid → wechat add → added (申请已发, 不发文案)
             → 无 contact_wxid → im_sent + "无联系方式"
  IM 未发完    → 保持 stage + "IM 已发 n/5" (下轮续发)
  add 失败     → im_done + reason (下轮续微信, IM 不重发)
"""

from __future__ import annotations

import time
from pathlib import Path

from .. import get_logger
from ..agents import client
from ..agents.retry import retry_result
from ..config import IM_MSG_COUNT, resolve_messages
from ..paths import CONTACTS_FILE
from ..state import RecruitState
from ..services import db, store

log = get_logger("invite")

_IM_INTERVAL = 3.0  # 两条 IM 消息之间间隔, 避免刷屏/风控


def _send_im_series(room_id: str, messages: list[str], progress: int, attempts: int
                    ) -> tuple[int, str | None]:
    """从小店 IM 发 messages[progress:], 返回 (已发送条数, 失败原因或 None)."""
    sent = progress
    for msg in messages[progress:]:
        res = retry_result(
            lambda: client.call("shop", "im_chat", room_id=room_id, message=msg),
            attempts=attempts, label=f"im:{room_id}",
        )
        if not res["success"]:
            return sent, res["error"] or "im_chat 失败"
        sent += 1
        if sent < len(messages):
            time.sleep(_IM_INTERVAL)
    return sent, None


def _invite_one(room: dict, messages: list[str], retry: int) -> dict:
    rid, key = room["roomId"], room["wxid"]
    cur = db.get_daren(key) or {}
    progress = int(cur.get("im_msgs_sent") or 0)

    sent, im_err = _send_im_series(rid, messages, progress, attempts=retry + 1)
    if sent < len(messages):
        # IM 未发完 → 记进度, 下轮从 im_msgs_sent 续发
        entry = db.upsert_daren(
            key, nickname=room["nickname"], room_id=rid, im_msgs_sent=sent,
            reason=f"IM 已发 {sent}/{len(messages)}: {im_err or ''}",
        )
        log.info("[%s] IM 发送中断 %d/%d: %s", room["nickname"], sent, len(messages), im_err)
        return entry

    # IM 全成功 → 先记满进度, 后续 save_mark 不再覆盖 im_msgs_sent
    db.upsert_daren(key, nickname=room["nickname"], room_id=rid, im_msgs_sent=sent)

    contact_wxid = (room.get("contact_wxid") or "").strip()
    if not contact_wxid:
        entry = store.save_mark(room, "im_sent", "无联系方式")
        log.info("[%s] IM %d 条已发, 无联系方式, 跳过微信", room["nickname"], len(messages))
        return entry

    add_res = retry_result(
        lambda: client.call("wechat", "add_friend", wxid=contact_wxid),
        attempts=retry + 1, label=f"add:{contact_wxid}",
    )
    if not add_res["success"]:
        entry = db.upsert_daren(
            key, nickname=room["nickname"], room_id=rid, stage="im_done",
            im_msgs_sent=sent, reason=f"微信加好友失败: {add_res['error'] or ''}",
        )
        log.error("[%s] 微信加好友失败: %s", room["nickname"], add_res["error"])
        return entry

    # 用户约束 (2026-08-13): 加好友只加好友, 不发送招商文案 —
    # 文案不能在好友申请中发出, 等对方通过好友后再跟进 (reply/手动 send_message)。
    entry = db.upsert_daren(
        key, nickname=room["nickname"], room_id=rid, stage="added",
        im_msgs_sent=sent, reason="好友申请已发送，待对方通过后跟进",
    )
    log.info("[%s] IM %d 条 + 微信好友申请已发 (未发文案, 待通过后跟进)", room["nickname"], len(messages))
    return entry


def _invite_done(wxid: str) -> bool:
    """invite 自己的完成判定: sent=微信已复邀, 或 im_sent+无联系方式=仅 IM 已邀.

    不复用 store.is_done (STAGES_DONE 里的 im_sent 会被旧 im 单条模式标上,
    若作 done 则 invite 永远跳过这批达人).
    """
    entry = db.get_daren(wxid) or {}
    if entry.get("stage") in ("sent", "added"):
        return True
    if entry.get("stage") == "im_sent" and "无联系方式" in (entry.get("reason") or ""):
        return True
    return False


def invite(state: RecruitState) -> dict:
    cfg = state["config"]
    messages = resolve_messages(cfg.text)[:IM_MSG_COUNT]
    if not messages:
        return {"error": "invite 需要招商文案 (每行一条, 每行 = 1 条 IM 消息)"}
    if len(messages) < IM_MSG_COUNT:
        log.warning("文案只有 %d 条 (<%d), invite 将按 %d 条发送", len(messages), IM_MSG_COUNT, len(messages))

    path = Path(cfg.contacts) if cfg.contacts else CONTACTS_FILE
    rooms = store.load_rooms(path)
    if not rooms:
        return {"error": f"contacts 里没有可用 roomId: {path}"}

    todo = [r for r in rooms if not _invite_done(r["wxid"])]
    if cfg.limit and cfg.limit > 0:
        todo = todo[:cfg.limit]
    if not todo:
        log.info("本轮没有待处理的 IM 房间 (全部已邀约)")
        return {"rooms": [], "todo": [], "results": {}}

    log.info("本轮 invite %d 个: %s", len(todo), ", ".join(r["nickname"] for r in todo))
    results: dict = {}
    for r in todo:
        results[r["wxid"]] = _invite_one(r, messages, cfg.retry)
    return {"rooms": todo, "todo": todo, "results": results}
