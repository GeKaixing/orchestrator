from pathlib import Path
import json
from fastapi import HTTPException
from recruit.paths import HOME, WECHAT_FRIEND_DIR, WXSHOP_DIR

FILES = {"wechat": WECHAT_FRIEND_DIR / ".env", "wxshop": WXSHOP_DIR / ".wxshop" / "api_config.json", "openwiki": HOME / ".openwiki" / ".env"}
SENSITIVE = ("key", "token", "secret", "password", "cookie", "authorization")

def _redact(obj):
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items()}
    return obj

def read_all() -> dict:
    out = {}
    for key, path in FILES.items():
        raw = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        if path.suffix == ".json":
            try: raw = json.dumps(_redact(json.loads(raw)), ensure_ascii=False, indent=2)
            except Exception: pass
        else:
            lines = []
            for line in raw.splitlines():
                lines.append(line)
            raw = "\n".join(lines)
        out[key] = {"path": str(path), "text": raw}
    out["rag"] = {"path": "外部服务 localhost:2024", "text": "配置由外部 RAG 服务管理"}
    return out

def write_config(key: str, text: str) -> dict:
    path = FILES.get(key)
    if not path: raise HTTPException(404, "不支持的 Agent")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"ok": True}
