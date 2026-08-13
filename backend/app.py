"""FastAPI 应用 — 全部 API 路由."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from recruit.paths import REPORT_FILE
from recruit.services import db

from . import agent_manager
from . import files as files_mod
from . import preflight as preflight_mod
from .runs import manager

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


app = FastAPI(title="recruit-backend", version="0.1.0", lifespan=_lifespan)
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


# ── 系统 ───────────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


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
