"""联系人装载 + 待办构建 + Send 扇出 + 汇合."""

from __future__ import annotations

from pathlib import Path

from langgraph.types import Send

from .. import get_logger
from ..paths import CONTACTS_FILE
from ..state import RecruitState
from ..services import store

log = get_logger("contacts")


def _contacts_path(state: RecruitState) -> Path:
    if state["config"].contacts:
        return Path(state["config"].contacts)
    return CONTACTS_FILE


def load_contacts(state: RecruitState) -> dict:
    path = _contacts_path(state)
    items = store.load_contacts(path)
    if not items:
        return {"error": f"contacts 里没有有效 wxId: {path}"}
    return {"contacts": items, "error": None}


def build_todo(state: RecruitState) -> dict:
    items = state.get("contacts") or []
    todo = [it for it in items if not store.is_done(it["wxid"])]
    limit = state["config"].limit
    if limit and limit > 0:
        todo = todo[:limit]
    if not todo:
        log.info("本轮没有待处理 wxid (全部已完成或达上限)")
    else:
        log.info("本轮待处理 %d 个: %s", len(todo), ", ".join(it["wxid"] for it in todo))
    return {"todo": todo}


def fan_out(state: RecruitState) -> list[Send] | str:
    """有待办则每人一个 Send 分支; scan 阶段只扫不发."""
    if state["config"].stage == "scan" or not state.get("todo"):
        return "report"
    actions = state["config"].actions_for()
    return [
        Send("process_contact", {"contact": c, "text": state["text"], "actions": actions,
                                 "retry": state["config"].retry})
        for c in state["todo"]
    ]


def join(state: RecruitState) -> dict:
    done = sum(1 for it in state.get("todo", [])
               if state.get("results", {}).get(it["wxid"], {}).get("stage") in ("sent", "im_sent"))
    log.info("全部联系人分支完成, 成功 %d/%d", done, len(state.get("todo", [])))
    return {}
