"""状态/数据文件读写 — 路径每次调用时经 paths 模块解析, 便于测试隔离."""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

from .. import get_logger
from .. import paths

log = get_logger("store")


# ── 状态持久化 ──────────────────────────────────────────────
def load_state() -> dict:
    f = paths.STATE_FILE
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            log.warning("读取 %s 失败: %s", f, e)
    return {}


def save_state(state: dict) -> None:
    f = paths.STATE_FILE
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark(contact: dict, stage: str, reason: str = "", updated: str | None = None) -> dict:
    """构造单个联系人的状态条目."""
    return {
        "wxid": contact["wxid"],
        "nickname": contact.get("nickname") or "?",
        **({"roomId": contact["roomId"]} if contact.get("roomId") else {}),
        "stage": stage,
        "reason": reason,
        "updated": updated or time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_mark(contact: dict, stage: str, reason: str = "") -> dict:
    """写入状态文件并返回新条目 (写穿)."""
    entry = mark(contact, stage, reason)
    st = load_state()
    st[contact["wxid"]] = entry
    save_state(st)
    return entry


def is_done(wxid: str) -> bool:
    st = load_state().get(wxid, {})
    return st.get("stage") in paths.STAGES_DONE


# ── 联系人/房间解析 ─────────────────────────────────────────
def load_contacts(path: Path) -> list[dict]:
    """读 contacts.jsonl, 提取有效 wxId (兼容 微信号/wxId/wx_id 字段, 剔除 (empty))."""
    rows = _read_jsonl(path)
    valid: list[dict] = []
    for r in rows:
        wxid = (r.get("wxId") or r.get("微信号") or r.get("wx_id") or "").strip()
        if not wxid or wxid.lower() == "(empty)":
            continue
        valid.append({"wxid": wxid, "nickname": (r.get("nickname") or "?").strip()})
    log.info("contacts: %d 行, 有效 wxId %d 个", len(rows), len(valid))
    return valid


def load_rooms(path: Path) -> list[dict]:
    """读 contacts 里有 roomId 的行 (小店官方 IM 房间), 供 im 招商."""
    rooms: list[dict] = []
    for r in _read_jsonl(path):
        rid = (r.get("roomId") or r.get("room_id") or "").strip()
        if rid:
            rooms.append({
                "roomId": rid,
                "nickname": (r.get("nickname") or "?").strip(),
                "wxid": f"im:{rid}",
            })
    log.info("rooms: %d 行, 可用 roomId %d 个", len(rooms), len(rooms))
    return rooms


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        log.error("文件不存在: %s", path)
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


# ── 报告 ────────────────────────────────────────────────────
def write_report(state: dict, todo: list[dict]) -> None:
    done_count = sum(1 for it in todo if state.get(it["wxid"], {}).get("stage") in paths.STAGES_DONE)
    lines = [
        "# 达人招商编排报告",
        "",
        f"- 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 本轮处理: {len(todo)} 个 (另 {done_count} 个此前已完成, 已跳过)",
        "",
        "| 微信号 | 昵称 | 阶段 | 备注 |",
        "|---|---|---|---|",
    ]
    for it in todo:
        wxid = it["wxid"]
        st = state.get(wxid, {})
        stage = st.get("stage", "pending")
        reason = st.get("reason", "") or ""
        lines.append(f"| {wxid} | {it['nickname']} | {stage} | {reason} |")
    lines.append("")
    counts: dict[str, int] = {}
    for it in todo:
        stage = state.get(it["wxid"], {}).get("stage", "pending")
        counts[stage] = counts.get(stage, 0) + 1
    lines.append("## 汇总")
    lines.append("")
    for k in sorted(counts):
        lines.append(f"- {k}: {counts[k]}")
    f = paths.REPORT_FILE
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines), encoding="utf-8")
    log.info("报告已生成: %s", f)
