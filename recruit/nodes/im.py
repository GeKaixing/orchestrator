"""小店官方 IM 招商节点 (stage=im): 逐个 im-chat 发招商文案."""

from __future__ import annotations

from pathlib import Path

from .. import get_logger
from ..paths import CONTACTS_FILE
from ..state import RecruitState
from ..services import store, wxshop

log = get_logger("im")


def im_recruit(state: RecruitState) -> dict:
    cfg = state["config"]
    path = Path(cfg.contacts) if cfg.contacts else CONTACTS_FILE
    rooms = store.load_rooms(path)
    if not rooms:
        return {"error": f"contacts 里没有可用 roomId: {path}"}

    todo = [r for r in rooms if not store.is_done(r["wxid"])]
    if cfg.limit and cfg.limit > 0:
        todo = todo[:cfg.limit]
    if not todo:
        log.info("本轮没有待发送的 IM 房间 (全部已发)")
        return {"rooms": [], "todo": [], "results": {}}

    log.info("本轮 IM 招商 %d 个: %s", len(todo), ", ".join(r["nickname"] for r in todo))
    results: dict = {}
    for r in todo:
        ok, reason = wxshop.im_chat(r["roomId"], state["text"])
        entry = store.save_mark(r, "im_sent" if ok else "failed", "" if ok else reason)
        results[r["wxid"]] = entry
        log.info("[%s] %s: %s", r["nickname"],
                 "IM 招商消息已发送" if ok else f"发送失败: {reason}")
    return {"rooms": todo, "todo": todo, "results": results}
