"""OpenWiki Agent — 包 recruit.services.openwiki, 统一 run(action, **params).

知识库问答统一走 openwiki agent 的 `query` 动作: openwiki (Personal 模式)
自己读 ~/.openwiki/wiki 本地知识脑定位页面并回答, 不再使用 hermes CLI.
"""

from __future__ import annotations

from typing import Any

from .. import get_logger
from ..services import openwiki
from .base import AgentResult, BaseAgent, fail, ok

log = get_logger("agents.openwiki")


class OpenWikiAgent(BaseAgent):
    name = "openwiki"

    def health(self) -> dict:
        ok_b, detail = openwiki._cli_ok()
        return {"ok": ok_b, "detail": detail}

    def run(self, action: str, **params: Any) -> AgentResult:
        if action == "query":
            question = str(params.get("question") or "").strip()
            if not question:
                return fail("问题不能为空")
            timeout = float(params.get("timeout") or 300)
            ok_b, reply = openwiki.query(question, timeout=timeout)
            return ok({"reply": reply}) if ok_b else fail(reply)
        return fail(f"未知动作: {action}")


agent = OpenWikiAgent()
