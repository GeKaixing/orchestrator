"""RAG Agent — 包 rag_client (wechat-friend-add/scripts), 统一 run(action, **params)."""

from __future__ import annotations

from typing import Any

from .. import get_logger
from ..services.runner import wechat_scripts_on_path
from .base import AgentResult, BaseAgent, fail, ok

log = get_logger("agents.rag")


def _rag():
    """惰性导入 rag_client (来自 wechat-friend-add/scripts)."""
    wechat_scripts_on_path()
    import rag_client  # type: ignore  # noqa: F401
    return rag_client


class RagAgent(BaseAgent):
    name = "rag"

    def health(self) -> dict:
        try:
            if _rag().available():
                return {"ok": True, "detail": "rag 服务可用 (localhost:2024)"}
            return {"ok": False, "detail": "rag 服务不可用 (localhost:2024)"}
        except Exception as e:  # noqa: BLE001
            log.error("rag health 异常: %s", e)
            return {"ok": False, "detail": f"health 异常: {e}"}

    def run(self, action: str, **params: Any) -> AgentResult:
        rc = _rag()
        if action == "available":
            return ok({"available": rc.available()})
        if action == "ask":
            result = rc.ask(params["question"], params.get("thread_id"), params.get("timeout"))
            if "error" in result:
                return fail(result["error"])
            return ok({"reply": result["reply"], "thread_id": result["thread_id"],
                       "run_id": result.get("run_id")})
        if action == "get_thread":
            return ok({"thread_id": rc.get_thread(params["key"])})
        if action == "set_thread":
            rc.set_thread(params["key"], params["thread_id"])
            return ok({})
        if action == "collapse_reply":
            return ok({"text": rc.collapse_reply(params["text"], params.get("max_chars"))})
        return fail(f"未知动作: {action}")


agent = RagAgent()
