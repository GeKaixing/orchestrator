"""Agent 协议基础 — AgentResult 与 BaseAgent 接口."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, TypedDict


class AgentResult(TypedDict):
    """统一动作返回: success + data 或 error."""

    success: bool
    data: dict
    error: str | None


def ok(data: dict | None = None) -> AgentResult:
    return {"success": True, "data": data or {}, "error": None}


def fail(error: str, data: dict | None = None) -> AgentResult:
    return {"success": False, "data": data or {}, "error": error}


class BaseAgent(ABC):
    """agent 统一接口. 子类只需实现 health 与 run."""

    name: str = ""

    @abstractmethod
    def health(self) -> dict:
        """返回 {ok, detail, checked_at}; ok=False 表示依赖不可用(降级), 非崩溃."""

    @abstractmethod
    def run(self, action: str, **params: Any) -> AgentResult:
        """执行一个动作, 返回 AgentResult."""

    def health_check(self) -> dict:
        h = self.health()
        h.setdefault("checked_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        h.setdefault("ok", False)
        return h
