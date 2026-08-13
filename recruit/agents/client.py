"""Agent 客户端 — orchestrator 节点与 AgentManager 共用的调用入口.

策略: 优先走 AgentManager 托管的 worker (读 db agents 表拿 port, TCP 调用);
worker 不存在/不可达/transport 异常 → 回落进程内直调同名 adapter (registry).
设 RECRUIT_AGENT_LOCAL=1 可强制直调 (测试/独立 CLI 用).
"""

from __future__ import annotations

import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor

from .. import get_logger
from ..services import db
from . import registry
from .base import AgentResult

log = get_logger("agents.client")

# 动作调用可能跑很久 (scan 最长 30min), 读超时放宽到长动作; 健康检查适中.
_CALL_TIMEOUT = 3600.0
_HEALTH_TIMEOUT = 20.0


def tcp_request(port: int, method: str, action: str | None = None,
                params: dict | None = None, timeout: float = _HEALTH_TIMEOUT) -> dict:
    """向 worker 发一个 JSON 行请求并返回 result; 失败抛异常 (由调用方决定兜底)."""
    req: dict = {"id": 1, "method": method}
    if action is not None:
        req["action"] = action
        req["params"] = params or {}
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
        f = sock.makefile("r", encoding="utf-8", errors="replace")
        line = f.readline()
        if not line:
            raise ConnectionError("worker 无响应")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise ConnectionError(resp.get("error") or "worker 调用失败")
        return resp.get("result")


def _worker_row(name: str) -> dict | None:
    if os.environ.get("RECRUIT_AGENT_LOCAL"):
        return None
    try:
        db.init_db()
        row = db.get_agent(name)
    except Exception:  # noqa: BLE001
        return None
    if row and row.get("status") == "running" and row.get("port"):
        return row
    return None


def call(name: str, action: str, **params: object) -> AgentResult:
    """执行 agent 动作, 返回 AgentResult. worker 优先, 失败回落直调."""
    row = _worker_row(name)
    if row:
        try:
            return tcp_request(row["port"], "call", action, params, timeout=_CALL_TIMEOUT)
        except Exception as e:  # noqa: BLE001
            log.warning("worker %s call(%s) 失败(%s), 回落进程内直调", name, action, e)
    return registry.get(name).run(action, **params)


def health(name: str) -> dict:
    """探测 agent 健康: {ok, detail, checked_at}. worker 优先, 失败回落直调."""
    row = _worker_row(name)
    if row:
        try:
            return tcp_request(row["port"], "health", timeout=_HEALTH_TIMEOUT)
        except Exception as e:  # noqa: BLE001
            log.warning("worker %s health 失败(%s), 回落进程内直调", name, e)
    return registry.get(name).health_check()


def health_all() -> dict[str, dict]:
    """并行探测全部 agent, 返回 {name: health} (用于 preflight/UI)."""
    out: dict[str, dict] = {}
    names = list(registry.REGISTRY)

    def _one(name: str) -> None:
        try:
            out[name] = health(name)
        except Exception as e:  # noqa: BLE001
            log.error("health %s 异常: %s", name, e)
            out[name] = {"ok": False, "detail": f"异常: {e}"}

    with ThreadPoolExecutor(max_workers=len(names) or 1) as ex:
        list(ex.map(_one, names))
    return out
