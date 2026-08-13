"""环境自检 — 基于三个托管 agent 的健康探测 (worker 优先, 回落直调)."""

from __future__ import annotations

from recruit.agents import client as agent_client


def run_checks() -> dict:
    healths = agent_client.health_all()
    return {
        "wechat": bool(healths.get("wechat", {}).get("ok")),
        "wxshop": bool(healths.get("shop", {}).get("ok")),
        "rag": bool(healths.get("rag", {}).get("ok")),
    }
