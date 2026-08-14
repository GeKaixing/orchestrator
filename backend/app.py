"""FastAPI 应用 — 全部 API 路由."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from recruit.paths import REPORT_FILE
from recruit.services import db
from recruit.services import followup as followup_mod

from . import agent_manager
from . import agent_store
from . import files as files_mod
from . import preflight as preflight_mod
from . import updates as updates_mod
from .runs import manager
from . import __version__

SETTING_KEYS = ("stage", "limit", "max_pages", "cat", "contacts", "text")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    db.init_db()
    try:
        agent_manager.manager.start_all()
    except Exception as e:  # noqa: BLE001
        print(f"[agent_manager] 启动异常: {e}", flush=True)
    yield
    agent_manager.manager.stop_all()


app = FastAPI(title="recruit-backend", version=__version__, lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求体 ─────────────────────────────────────────────────
class RunPayload(BaseModel):
    type: str = "recruit"   # recruit | reply
    stage: str = "all"
    limit: int = 10
    max_pages: int = 1
    cat: str = ""
    contacts: str = ""
    text: str = ""


class SettingsPayload(BaseModel):
    stage: str = "all"
    limit: int = 10
    max_pages: int = 1
    cat: str = ""
    contacts: str = ""
    text: str = ""


class WxshopRunPayload(BaseModel):
    argv: list[str] = []
    timeout: int = 600


class RagAskPayload(BaseModel):
    question: str
    thread_id: str | None = None
    timeout: int | None = None


# ── 系统 ───────────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/update-check")
def update_check(force: int = 0) -> dict:
    return updates_mod.check_update(force=bool(force))


@app.get("/api/preflight")
def preflight() -> dict:
    return preflight_mod.run_checks()


# ── Agent 管理 ──────────────────────────────────────────────
@app.get("/api/agents")
def agents() -> list[dict]:
    return agent_manager.manager.status_all()


@app.get("/api/agents/{name}/health")
def agent_health(name: str) -> dict:
    if name not in agent_manager.AGENT_NAMES:
        raise HTTPException(status_code=404, detail=f"未知 agent: {name}")
    return _live_health(name)


def _live_health(name: str) -> dict:
    from recruit.agents import client as agent_client
    try:
        return agent_client.health(name)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"异常: {e}"}


@app.post("/api/agents/{name}/start")
def agent_start(name: str) -> dict:
    if name not in agent_manager.AGENT_NAMES:
        raise HTTPException(status_code=404, detail=f"未知 agent: {name}")
    return agent_manager.manager.start(name)


@app.post("/api/agents/{name}/stop")
def agent_stop(name: str) -> dict:
    if name not in agent_manager.AGENT_NAMES:
        raise HTTPException(status_code=404, detail=f"未知 agent: {name}")
    return agent_manager.manager.stop(name)


@app.post("/api/agents/{name}/restart")
def agent_restart(name: str) -> dict:
    if name not in agent_manager.AGENT_NAMES:
        raise HTTPException(status_code=404, detail=f"未知 agent: {name}")
    return agent_manager.manager.restart(name)


@app.post("/api/agents/rag/ask")
def rag_ask(payload: RagAskPayload) -> dict:
    """提交问题给 RAG 知识库, 返回 {reply, thread_id}. thread_id 为空则新建线程."""
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    from recruit.agents import client as agent_client
    result = agent_client.call(
        "rag", "ask",
        question=payload.question,
        thread_id=payload.thread_id,
        timeout=payload.timeout,
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "RAG 调用失败")
    return result.get("data") or {}


@app.post("/api/agents/wiki/ask")
def wiki_ask(payload: RagAskPayload) -> dict:
    """向本地知识库提问 (统一走 hermes agent 的 query 动作).

    Hermes 自己读 Obsidian 知识库 (llm-wiki) 定位页面并回答, 引用来源页面;
    不再使用独立 wiki agent (已废弃). 端点路径保留兼容旧调用.
    """
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    from recruit.agents import client as agent_client
    result = agent_client.call(
        "hermes", "query",
        question=payload.question,
        timeout=payload.timeout or 300,
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error") or "知识库问答失败")
    return result.get("data") or {}


# ── 监控 ───────────────────────────────────────────────────
@app.get("/api/stats")
def stats() -> dict:
    st = db.get_state()
    counts: dict[str, int] = {}
    for v in st.values():
        s = v.get("stage") or "pending"
        counts[s] = counts.get(s, 0) + 1
    return {
        "total": len(st),
        "pending": counts.get("pending", 0),
        "added": counts.get("added", 0),
        "sent": counts.get("sent", 0),
        "im_sent": counts.get("im_sent", 0),
        "failed": counts.get("failed", 0),
        "by_stage": counts,
    }


@app.get("/api/darens")
def darens(stage: str | None = None, q: str | None = None,
           limit: int = Query(default=2000, le=10000)) -> list[dict]:
    return db.get_darens(stage=stage, q=q, limit=limit)


# ── 任务 ───────────────────────────────────────────────────
@app.get("/api/runs")
def runs(limit: int = 50) -> list[dict]:
    return db.get_runs(limit=limit)


@app.post("/api/runs")
def create_run(payload: RunPayload) -> dict:
    return manager.start(payload.model_dump())


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int) -> dict:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} 不存在")
    return run


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: int) -> dict:
    return manager.stop(run_id)


@app.get("/api/runs/{run_id}/logs")
def run_logs(run_id: int, after: int = 0, limit: int = 500) -> dict:
    logs = db.get_logs(run_id, after=after, limit=limit)
    next_after = logs[-1]["id"] if logs else after
    return {"run_id": run_id, "logs": logs, "next": next_after}


# ── 报告 / 数据 ────────────────────────────────────────────
@app.get("/api/report")
def report() -> dict:
    if REPORT_FILE.exists():
        return {"text": REPORT_FILE.read_text(encoding="utf-8", errors="replace")}
    return {"text": f"(报告文件不存在: {REPORT_FILE})"}


# 跟进表可视化的关键列 (48 列里挑展示用)
_FOLLOWUP_COLS = (
    "达人昵称", "微信号", "手机号", "跟进状态", "备注原因", "达人评分",
    "带货销售额", "粉丝数", "采集时间", "登记时间", "来源页面", "达人等级",
)


@app.get("/api/followup")
def followup(q: str | None = None, status: str | None = None,
             limit: int = Query(default=500, le=5000)) -> dict:
    """达人跟进表 (wxshop-cli/达人跟进表.db). 支持昵称/微信号/手机号搜索 + 状态过滤."""
    rows = followup_mod.list_darens()
    out: list[dict] = []
    for r in rows:
        if q:
            hay = f"{r.get('达人昵称') or ''} {r.get('微信号') or ''} {r.get('手机号') or ''}"
            if q.strip() not in hay:
                continue
        if status and (r.get("跟进状态") or "") != status:
            continue
        out.append({k: r.get(k) for k in _FOLLOWUP_COLS})
    stats: dict[str, int] = {}
    for r in rows:
        s = r.get("跟进状态") or "(未标记)"
        stats[s] = stats.get(s, 0) + 1
    return {"total": len(rows), "shown": len(out), "rows": out[:limit], "stats": stats}


@app.get("/api/files")
def files(name: str) -> dict:
    return files_mod.read(name)


# ── 设置 ───────────────────────────────────────────────────
@app.get("/api/settings")
def get_settings() -> dict:
    out = {}
    for k in SETTING_KEYS:
        out[k] = db.get_setting(k)
    return out


@app.put("/api/settings")
def put_settings(payload: SettingsPayload) -> dict:
    data = payload.model_dump()
    for k, v in data.items():
        db.set_setting(k, v)
    return data


# ── 子 Agent 下载 ──────────────────────────────────────────
@app.get("/api/agent-store")
def agent_store_list() -> list[dict]:
    return agent_store.list_agents()


def _store_action(key: str, action: str) -> dict:
    try:
        agent_store._get(key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return getattr(agent_store, action)(key)


@app.post("/api/agent-store/{key}/install")
def agent_store_install(key: str) -> dict:
    return _store_action(key, "install")


@app.post("/api/agent-store/{key}/update")
def agent_store_update(key: str) -> dict:
    return _store_action(key, "update")


@app.post("/api/agent-store/{key}/remove")
def agent_store_remove(key: str) -> dict:
    return _store_action(key, "remove")


# ── wxshop CLI 调试 ─────────────────────────────────────────
@app.post("/api/wxshop/run")
def wxshop_run(payload: WxshopRunPayload) -> dict:
    from . import wxshop_debug
    return wxshop_debug.run(payload.argv, timeout=min(payload.timeout, 900))
