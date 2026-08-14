"""报告生成节点."""

from __future__ import annotations

from .. import get_logger
from ..state import RecruitState
from ..services import store

log = get_logger("report")


def report(state: RecruitState) -> dict:
    merged = {**store.load_state(), **state.get("results", {})}
    note = ""
    if state.get("no_contacts"):
        note = f"⚠ 未提取到联系方式, 但 {state.get('scan_saved') or 0} 条达人画像已存进跟进表 (联系方式列留空)"
    store.write_report(merged, state.get("todo") or [], note=note)
    log.info("报告已生成: %s", "recruit_report.md")
    return {}
