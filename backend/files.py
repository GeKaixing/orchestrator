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
        return {"name": name, "count": 0, "text": f"(文件不存在: {path})"}
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    count = len(lines)
    if name == "state" and count == 1:
        try:
            obj = json.loads(lines[0])
            count = len(obj) if isinstance(obj, (dict, list)) else count
        except Exception:  # noqa: BLE001
            pass
    return {"name": name, "count": count, "text": raw}
