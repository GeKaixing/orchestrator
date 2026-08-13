"""python -m backend 入口 — 启动 uvicorn."""

from __future__ import annotations

import os
import sys

PORT = int(os.environ.get("RECRUIT_BACKEND_PORT", "8765"))


def main() -> int:
    import uvicorn

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uvicorn.run("backend.app:app", host="127.0.0.1", port=PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
