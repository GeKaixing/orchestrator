"""invite 阶段 (stage=invite): 小店 IM 固定文案邀约 → 联系方式 → 微信加好友.

需求映射:
  5. 在进入 IM 页后给达人发送 5 条邀约带货信息 (用户自定义, 每行一条).
  7. 进入 IM 页后将获取的达人联系方式 (手机号/微信号) 放入跟进表对应列;
     没有则空着; 都没有 → 跳过微信加好友, 标记后进入下一个.
  8. 微信自动化添加: 微信号优先, 只有手机号则用手机号; 都没有 → 跳过.
  9. 加好友失败 (注销/频繁/隐私等) → 在跟进表标记该用户 → 继续下一个.
  10. 微信中不主动发聊天内容 (加好友申请成功后等待对方通过再跟进).

IM 发送进度写穿 darens.im_msgs_sent, 中断后续发不重发.
"""

from __future__ import annotations

import time
from pathlib import Path

from .. import get_logger
from ..agents import client
from ..agents.retry import retry_result
from ..config import IM_MSG_COUNT, resolve_messages
from ..paths import CONTACTS_FILE
from ..services import accounts, db, followup, store
from ..state import RecruitState

log = get_logger("invite")

_IM_INTERVAL = 3.0  # 两条 IM 消息之间间隔, 避免刷屏/风控


def _send_im_series(room_id: str, messages: list[str], progress: int, attempts: int,
                    account: str) -> tuple[int, str | None]:
    """从小店 IM 发 messages[progress:], 返回 (已发送条数, 失败原因或 None)."""
    sent = progress
    for msg in messages[progress:]:
        res = retry_result(
            lambda: client.call("shop", "im_chat", room_id=room_id, message=msg,
                                account=account),
            attempts=attempts, label=f"im:{room_id}",
        )
        if not res["success"]:
            return sent, res["error"] or "im_chat 失败"
        sent += 1
        if sent < len(messages):
            time.sleep(_IM_INTERVAL)
    return sent, None


def _invite_one(room: dict, messages: list[str], retry: int, account: str) -> dict:
    rid, key = room["roomId"], room["wxid"]
    nick = room["nickname"]
    cur = db.get_daren(key) or {}
    progress = int(cur.get("im_msgs_sent") or 0)

    # ── 1) IM 5 句邀约 (进度续发) ──
    sent, im_err = _send_im_series(rid, messages, progress, attempts=retry + 1,
                                   account=account)
    if sent < len(messages):
        # IM 未发完 → 记进度, 下轮从 im_msgs_sent 续发
        entry = db.upsert_daren(
            key, nickname=nick, room_id=rid, im_msgs_sent=sent,
            reason=f"IM 已发 {sent}/{len(messages)}: {im_err or ''}",
        )
        followup.mark_status(nick, "IM邀约中", f"IM 已发 {sent}/{len(messages)}")
        log.info("[%s] IM 发送中断 %d/%d: %s", nick, sent, len(messages), im_err)
        return entry

    # IM 全成功 → 先记满进度, 后续 save_mark 不再覆盖 im_msgs_sent
    db.upsert_daren(key, nickname=nick, room_id=rid, im_msgs_sent=sent)

    # ── 2) 联系方式写入跟进表 (微信号/手机号列, 空则留空) ──
    cwxid = (room.get("contact_wxid") or "").strip()
    phone = (room.get("phone") or "").strip()
    followup.upsert_daren(room, {"微信号": cwxid, "手机号": phone})

    # ── 3) 微信加好友: 微信号优先, 否则手机号; 都没有 → 跳过 ──
    target = cwxid or phone
    if not target:
        entry = store.save_mark(room, "im_sent", "无联系方式")
        followup.mark_status(nick, "已邀约", "无联系方式, 跳过微信加好友")
        log.info("[%s] IM %d 条已发, 无联系方式, 跳过微信", nick, len(messages))
        return entry

    add_res = retry_result(
        lambda: client.call("wechat", "add_friend", wxid=target),
        attempts=retry + 1, label=f"add:{target}",
    )
    if not add_res["success"]:
        reason = add_res["error"] or "加好友失败"
        entry = db.upsert_daren(
            key, nickname=nick, room_id=rid, stage="im_done",
            im_msgs_sent=sent, reason=f"微信加好友失败: {reason}",
        )
        followup.mark_status(nick, "添加失败", reason)
        log.error("[%s] 微信加好友失败: %s", nick, reason)
        return entry

    # 需求10: 只加好友, 不发送招商文案 — 等对方通过好友后再跟进
    entry = db.upsert_daren(
        key, nickname=nick, room_id=rid, stage="added",
        im_msgs_sent=sent, reason="好友申请已发送，待对方通过后跟进",
    )
    followup.mark_status(nick, "已加好友", "好友申请已发送，待对方通过后跟进")
    log.info("[%s] IM %d 条 + 微信好友申请已发 (目标 %s, 未发文案)", nick, len(messages), target)
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
    account = accounts.current()
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

    log.info("本轮 invite %d 个 (账号 %s): %s", len(todo), account,
             ", ".join(r["nickname"] for r in todo))
    results: dict = {}
    for r in todo:
        results[r["wxid"]] = _invite_one(r, messages, cfg.retry, account)
    return {"rooms": todo, "todo": todo, "results": results}