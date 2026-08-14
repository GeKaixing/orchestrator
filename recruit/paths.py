"""路径常量 — 在调用时解析, 便于测试 monkeypatch 隔离."""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # orchestrator/ 所在目录 (包内/桌面均可)


def _sibling(name: str) -> Path:
    """依赖项目解析: 现在集中放在 orchestrator/agents/ 下 (用户已移动).

    依次回退: agents/ → 与 orchestrator 同级 (旧布局) → ~/Desktop. 返回存在的第一个.
    """
    for cand in (
        PROJECT_ROOT / "agents" / name,
        PROJECT_ROOT.parent / name,
        HOME / "Desktop" / name,
    ):
        if cand.is_dir():
            return cand
    return PROJECT_ROOT / "agents" / name  # 默认新布局


WORK_DIR = PROJECT_ROOT
WXSHOP_DIR = _sibling("wxshop-cli")
WECHAT_FRIEND_DIR = _sibling("wechat-friend-add")
RAG_DIR = _sibling("rag")
WIKI_DIR = _sibling("wiki")
# 知识源优先用本地 Obsidian 知识库 (llm-wiki, 原 openwiki OKF wiki 的替代);
# 不存在时回退 agents/wiki (openwiki 生成的旧结构)
if (HOME / "wiki").is_dir():
    WIKI_DIR = HOME / "wiki"
# llm-wiki 的 markdown 直接散在根 + entities/concepts/… 子目录 (非 OKF 的 wiki/ 子目录)
WIKI_CONTENT_DIR = WIKI_DIR / "wiki" if (WIKI_DIR / "wiki").is_dir() else WIKI_DIR
WECHAT_SCRIPTS_DIR = WECHAT_FRIEND_DIR / "scripts"

TALENTS_FILE = WORK_DIR / "talents.jsonl"
CONTACTS_FILE = WORK_DIR / "contacts.jsonl"
STATE_FILE = WORK_DIR / "recruit_state.json"
REPORT_FILE = WORK_DIR / "recruit_report.md"
DB_FILE = WORK_DIR / "recruit.db"

# 达人跟进表.db 由 wxshop-cli 维护 (48 列, daren-scan --db 写入); orchestrator 直接读写它
FOLLOWUP_DB = WXSHOP_DIR / "达人跟进表.db"
FOLLOWUP_TABLE = "达人跟进表"

# wxshop 登录态目录: 项目内 .wxshop/ (default) + .wxshop/accounts/<name>/ (多账号)
WXSHOP_STATE_DIR = WXSHOP_DIR / ".wxshop"
# 当前选中的小店账号 (持久化在 settings 表, 这里只是缺省值)
DEFAULT_WXSHOP_ACCOUNT = "default"

# 已完成阶段: 命中即跳过 (added = 好友申请已发, 待对方通过后跟进, 不再重发)
STAGES_DONE = {"sent", "im_sent", "added"}
