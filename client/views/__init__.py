"""客户端视图 — 各功能页."""

from __future__ import annotations

UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"

STAGE_LABELS = {
    "pending": "待处理",
    "added": "已加好友",
    "sent": "已发文案",
    "im_sent": "IM已发",
    "failed": "失败",
}

STAGE_COLORS = {
    "pending": "#9aa0a6",
    "added": "#7c9ff2",
    "sent": "#3ddc84",
    "im_sent": "#2ec5c5",
    "failed": "#ff6b6b",
}

STAGE_ORDER = ["pending", "added", "sent", "im_sent", "failed"]
