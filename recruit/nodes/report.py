"""报告生成节点."""

from __future__ import annotations

from .. import get_logger
from ..state import RecruitState
from ..services import store

log = get_logger("report")


def report(state: RecruitState) -> dict:
    merged = {**store.load_state(), **state.get("results", {})}
    store.write_report(merged, state.get("todo") or [])
    log.info("报告已生成: %s", "recruit_report.md")
    return {}
