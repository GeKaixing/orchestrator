"""数据文件读取 — 按白名单返回 contacts/talents/state 原始内容."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from recruit.paths import CONTACTS_FILE, STATE_FILE, TALENTS_FILE

FILES: dict[str, Path] = {
    "contacts": CONTACTS_FILE,
    "talents": TALENTS_FILE,
    "state": STATE_FILE,
}


def read(name: str) -> dict:
    path = FILES.get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"未知文件: {name}")
    if not path.exists():
        return {"name": name, "count": 0, "rows": [], "text": f"(文件不存在: {path})"}
    raw = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict] = []
    if name == "state":
        # state 是单文档 JSON (pretty-printed 字典/数组), 整份解析
        try:
            obj = json.loads(raw)
        except Exception:  # noqa: BLE001
            obj = None
        if isinstance(obj, dict):
            rows = [v for v in obj.values() if isinstance(v, dict)]
        elif isinstance(obj, list):
            rows = [o for o in obj if isinstance(o, dict)]
    else:
        # contacts/talents 是 JSONL, 逐行解析
        for ln in raw.splitlines():
            if not ln.strip():
                continue
            try:
                obj = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return {"name": name, "count": len(rows), "rows": rows, "text": raw}
