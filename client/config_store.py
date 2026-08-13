"""客户端配置持久化 — orchestrator/client_config.json."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent / "client_config.json"

DEFAULTS: dict = {
    "text": "",        # 招商文案
    "stage": "all",    # all/scan/add/send/im
    "limit": 10,
    "max_pages": 1,
    "cat": "",
    "contacts": "",
}


def load() -> dict:
    """读取配置, 缺失字段回退默认值."""
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
        for k in data:
            if k in cfg:
                cfg[k] = data[k]
    return cfg


def save(cfg: dict) -> None:
    """写回配置 (仅保留已知字段)."""
    cleaned = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2),
                           encoding="utf-8")
