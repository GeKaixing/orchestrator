"""wxshop 扫描阶段: scan → backfill_room_ids → contact."""

from __future__ import annotations

from .. import get_logger
from ..agents import client
from ..paths import CONTACTS_FILE, TALENTS_FILE
from ..state import RecruitState

log = get_logger("scan")


def scan(state: RecruitState) -> dict:
    cfg = state["config"]
    log.info("── 阶段一: wxshop 扫描达人 + 提取联系方式 ──")
    if not client.call("shop", "scan", cat=cfg.cat or None,
                       max_pages=cfg.max_pages, out=str(TALENTS_FILE))["success"]:
        return {"error": "daren-scan 失败"}
    if not client.call("shop", "backfill_room_ids", path=str(TALENTS_FILE))["success"]:
        return {"error": "没有可从 imUrl 提取的 roomId"}
    if not client.call("shop", "contact", in_path=str(TALENTS_FILE),
                       out_path=str(CONTACTS_FILE))["success"]:
        return {"error": "daren-contact 失败 (可能命中每日提取上限)"}
    log.info("阶段一完成: %s", CONTACTS_FILE)
    return {"error": None}
