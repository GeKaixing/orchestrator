"""SQLite 持久层 — darens / runs / run_logs / settings.

多进程共用 recruit.db (WAL 模式):
- 编排子进程写 darens (store.save_mark 写穿)
- 后端进程写 runs / run_logs / settings, 读 darens
每次调用短连接, 避免跨线程持有连接.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from .. import get_logger
from .. import paths

log = get_logger("db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS darens (
    wxid TEXT PRIMARY KEY,
    nickname TEXT NOT NULL DEFAULT '?',
    room_id TEXT,
    stage TEXT NOT NULL DEFAULT 'pending',
    reason TEXT NOT NULL DEFAULT '',
    updated TEXT NOT NULL DEFAULT '',
    replied_msg_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL DEFAULT 'recruit',
    stage TEXT NOT NULL DEFAULT '',
    "limit" INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    exit_code INTEGER,
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT,
    summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ts TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'stopped',
    pid INTEGER,
    port INTEGER,
    detail TEXT NOT NULL DEFAULT '',
    last_health TEXT NOT NULL DEFAULT '',
    updated TEXT NOT NULL DEFAULT ''
);
"""

_init_done = False


def _connect() -> sqlite3.Connection:
    paths.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(paths.DB_FILE), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db() -> None:
    """建表 + 首次导入旧 JSON 状态. 幂等."""
    global _init_done
    if _init_done:
        return
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _import_legacy(conn)
    finally:
        conn.close()
    _init_done = True


def _import_legacy(conn: sqlite3.Connection) -> None:
    """若存在旧 recruit_state.json 且 darens 为空, 一次性导入."""
    f = paths.STATE_FILE
    if not f.exists():
        return
    if conn.execute("SELECT COUNT(*) AS c FROM darens").fetchone()["c"] > 0:
        return
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("旧状态导入失败: %s", e)
        return
    n = 0
    for wxid, st in data.items():
        conn.execute(
            "INSERT OR IGNORE INTO darens (wxid, nickname, room_id, stage, reason, updated, replied_msg_ids) "
            "VALUES (?,?,?,?,?,?,?)",
            (wxid, st.get("nickname") or "?", st.get("roomId"),
             st.get("stage") or "pending", st.get("reason") or "", st.get("updated") or "",
             json.dumps(st.get("replied_msg_ids") or [], ensure_ascii=False)),
        )
        n += 1
    conn.commit()
    log.info("从 recruit_state.json 导入 %d 条 darens", n)


def _row_to_entry(row: sqlite3.Row) -> dict:
    d = dict(row)
    entry: dict = {
        "wxid": d["wxid"],
        "nickname": d["nickname"],
        "stage": d["stage"],
        "reason": d["reason"],
        "updated": d["updated"],
    }
    if d.get("room_id"):
        entry["roomId"] = d["room_id"]
    try:
        entry["replied_msg_ids"] = json.loads(d["replied_msg_ids"] or "[]")
    except Exception:  # noqa: BLE001
        entry["replied_msg_ids"] = []
    return entry


# ── darens ─────────────────────────────────────────────────
def upsert_daren(wxid: str, **fields: Any) -> dict:
    """按 wxid upsert daren, 返回旧形状条目 (wxid/nickname/roomId/stage/reason/updated)."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM darens WHERE wxid=?", (wxid,)).fetchone()
        cur: dict[str, Any] = dict(row) if row else {
            "wxid": wxid, "nickname": fields.get("nickname") or "?",
            "room_id": fields.get("room_id"), "stage": "pending",
            "reason": "", "updated": "", "replied_msg_ids": "[]",
        }
        for k in ("nickname", "room_id", "stage", "reason", "updated"):
            if fields.get(k) is not None:
                cur[k] = fields[k]
        if fields.get("replied_msg_ids") is not None:
            cur["replied_msg_ids"] = json.dumps(fields["replied_msg_ids"], ensure_ascii=False)
        if not cur["updated"]:
            cur["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO darens (wxid, nickname, room_id, stage, reason, updated, replied_msg_ids) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(wxid) DO UPDATE SET nickname=excluded.nickname, room_id=excluded.room_id, "
            "stage=excluded.stage, reason=excluded.reason, updated=excluded.updated, "
            "replied_msg_ids=excluded.replied_msg_ids",
            (cur["wxid"], cur["nickname"], cur["room_id"], cur["stage"], cur["reason"],
             cur["updated"], cur["replied_msg_ids"]),
        )
        conn.commit()
        return _row_to_entry(conn.execute("SELECT * FROM darens WHERE wxid=?", (wxid,)).fetchone())
    finally:
        conn.close()


def get_daren(wxid: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM darens WHERE wxid=?", (wxid,)).fetchone()
        return _row_to_entry(row) if row else None
    finally:
        conn.close()


def get_state() -> dict[str, dict]:
    """返回 {wxid: entry}, 兼容旧 load_state 形状."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM darens").fetchall()
        return {r["wxid"]: _row_to_entry(r) for r in rows}
    finally:
        conn.close()


def get_darens(stage: str | None = None, q: str | None = None, limit: int = 2000) -> list[dict]:
    conn = _connect()
    try:
        sql = "SELECT * FROM darens"
        conds, values = [], []
        if stage:
            conds.append("stage=?")
            values.append(stage)
        if q:
            conds.append("(nickname LIKE ? OR wxid LIKE ?)")
            values += [f"%{q}%", f"%{q}%"]
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY updated DESC LIMIT ?"
        values.append(limit)
        rows = conn.execute(sql, values).fetchall()
        return [_row_to_entry(r) for r in rows]
    finally:
        conn.close()


# ── runs ───────────────────────────────────────────────────
def insert_run(run_type: str, stage: str, limit: int | None, summary: str = "") -> int:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    try:
        cur = conn.execute(
            'INSERT INTO runs (run_type, stage, "limit", status, started_at, summary) VALUES (?,?,?,?,?,?)',
            (run_type, stage, limit, "running", now, summary),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_run(run_id: int, **fields: Any) -> None:
    allowed = {"status", "exit_code", "finished_at", "summary"}
    sets = [f"{k}=?" for k in fields if k in allowed]
    if not sets:
        return
    values = [fields[k] for k in fields if k in allowed] + [run_id]
    conn = _connect()
    try:
        conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id=?", values)
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_runs(limit: int = 50) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── run_logs ───────────────────────────────────────────────
def insert_log(run_id: int, message: str, level: str = "INFO") -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    try:
        conn.execute("INSERT INTO run_logs (run_id, ts, level, message) VALUES (?,?,?,?)",
                     (run_id, now, level, message))
        conn.commit()
    finally:
        conn.close()


def get_logs(run_id: int, after: int = 0, limit: int = 500) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM run_logs WHERE run_id=? AND id>? ORDER BY id LIMIT ?",
            (run_id, after, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── settings ───────────────────────────────────────────────
def get_setting(key: str, default: str = "") -> str:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: Any) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        conn.commit()
    finally:
        conn.close()


# ── agents ──────────────────────────────────────────────────
def upsert_agent(name: str, **fields: Any) -> dict:
    """写穿 agent 状态行 (status/pid/port/detail/last_health), 返回新行."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
        cur: dict[str, Any] = dict(row) if row else {
            "name": name, "status": "stopped", "pid": None, "port": None,
            "detail": "", "last_health": "", "updated": "",
        }
        for k in ("status", "pid", "port", "detail", "last_health"):
            if fields.get(k) is not None:
                cur[k] = fields[k]
        cur["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO agents (name, status, pid, port, detail, last_health, updated) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET status=excluded.status, pid=excluded.pid, "
            "port=excluded.port, detail=excluded.detail, last_health=excluded.last_health, "
            "updated=excluded.updated",
            (cur["name"], cur["status"], cur["pid"], cur["port"], cur["detail"],
             cur["last_health"], cur["updated"]),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone())
    finally:
        conn.close()


def get_agent(name: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_agents() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
