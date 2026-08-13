"""路径常量 — 在调用时解析, 便于测试 monkeypatch 隔离."""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

WORK_DIR = Path(os.path.expanduser("~/Desktop/orchestrator"))
WXSHOP_DIR = Path(os.path.expanduser("~/Desktop/wxshop-cli"))
WECHAT_FRIEND_DIR = Path(os.path.expanduser("~/Desktop/wechat-friend-add"))
WECHAT_SCRIPTS_DIR = WECHAT_FRIEND_DIR / "scripts"

TALENTS_FILE = WORK_DIR / "talents.jsonl"
CONTACTS_FILE = WORK_DIR / "contacts.jsonl"
STATE_FILE = WORK_DIR / "recruit_state.json"
REPORT_FILE = WORK_DIR / "recruit_report.md"
DB_FILE = WORK_DIR / "recruit.db"

# 已完成阶段: 命中即跳过
STAGES_DONE = {"sent", "im_sent"}
