"""Agent 注册表 — 名字 → BaseAgent 实例; health_all 并行."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from .. import get_logger
from .base import BaseAgent
from .rag import agent as rag_agent
from .shop import agent as shop_agent
from .wechat import agent as wechat_agent

log = get_logger("agents")

REGISTRY: dict[str, BaseAgent] = {
    a.name: a for a in (wechat_agent, shop_agent, rag_agent)
}


def get(name: str) -> BaseAgent:
    if name not in REGISTRY:
        raise KeyError(f"未知 agent: {name} (可选: {', '.join(REGISTRY)})")
    return REGISTRY[name]


def health(name: str) -> dict:
    return get(name).health_check()


def health_all(max_workers: int = 3) -> dict[str, dict]:
    """并行探测全部 agent 健康, 返回 {name: {ok, detail, checked_at}}."""
    out: dict[str, dict] = {}

    def _one(name: str) -> None:
        try:
            out[name] = health(name)
        except Exception as e:  # noqa: BLE001
            log.error("health %s 异常: %s", name, e)
            out[name] = {"ok": False, "detail": f"异常: {e}",
                         "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(_one, list(REGISTRY)))
    return out
