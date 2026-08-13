"""路径常量 — 在调用时解析, 便于测试 monkeypatch 隔离."""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # orchestrator/ 所在目录 (包内/桌面均可)


def _sibling(name: str) -> Path:
    """优先取与 orchestrator 同级的目录 (可随分发包整体搬移), 兜底回退 ~/Desktop."""
    p = PROJECT_ROOT.parent / name
    if p.is_dir():
        return p
    return HOME / "Desktop" / name


WORK_DIR = PROJECT_ROOT
WXSHOP_DIR = _sibling("wxshop-cli")
WECHAT_FRIEND_DIR = _sibling("wechat-friend-add")
RAG_DIR = _sibling("rag")
WECHAT_SCRIPTS_DIR = WECHAT_FRIEND_DIR / "scripts"

TALENTS_FILE = WORK_DIR / "talents.jsonl"
CONTACTS_FILE = WORK_DIR / "contacts.jsonl"
STATE_FILE = WORK_DIR / "recruit_state.json"
REPORT_FILE = WORK_DIR / "recruit_report.md"
DB_FILE = WORK_DIR / "recruit.db"

# 已完成阶段: 命中即跳过 (added = 好友申请已发, 待对方通过后跟进, 不再重发)
STAGES_DONE = {"sent", "im_sent", "added"}
