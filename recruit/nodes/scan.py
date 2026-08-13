"""wxshop 扫描阶段: scan → backfill_room_ids → contact."""

from __future__ import annotations

from .. import get_logger
from ..paths import CONTACTS_FILE, TALENTS_FILE
from ..state import RecruitState
from ..services import wxshop

log = get_logger("scan")


def scan(state: RecruitState) -> dict:
    log.info("── 阶段一: wxshop 扫描达人 + 提取联系方式 ──")
    if not wxshop.scan(TALENTS_FILE, state["config"].cat or None, state["config"].max_pages):
        return {"error": "daren-scan 失败"}
    if not wxshop.backfill_room_ids(TALENTS_FILE):
        return {"error": "没有可从 imUrl 提取的 roomId"}
    if not wxshop.contact(TALENTS_FILE, CONTACTS_FILE):
        return {"error": "daren-contact 失败 (可能命中每日提取上限)"}
    log.info("阶段一完成: %s", CONTACTS_FILE)
    return {"error": None}
