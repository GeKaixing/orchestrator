"""openwiki CLI 封装 — Personal 模式本地知识脑问答 (agents/openwiki 子项目).

用法: npx openwiki personal "<问题>" 一次性问答, 答案在 stdout.
知识库: ~/.openwiki/wiki (由 ingest 从 ~/wiki 等源合成); 配置在 ~/.openwiki/.env.
"""

from __future__ import annotations

import re
import os
import shutil
import subprocess

from .. import get_logger
from ..paths import OPENWIKI_DIR

log = get_logger("openwiki")

# openwiki 启动 banner 以 ASCII art + 圆角边框盒结尾 (╰──…╯ 行); 答案在其后.
_BANNER_END = re.compile(r"^[╰└].*╯$")


def _strip_banner(out: str) -> str:
    """剥离 openwiki 启动 banner, 返回答案正文 (banner 在开头时)."""
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if _BANNER_END.match(line.strip()):
            return "\n".join(lines[i + 1:]).strip()
    return out.strip()


def _cli_ok() -> tuple[bool, str]:
    """判定 openwiki 子项目是否就绪 (目录存在 + CLI 依赖已装)."""
    if not OPENWIKI_DIR.is_dir():
        return False, f"openwiki 未安装 ({OPENWIKI_DIR})"
    if not (OPENWIKI_DIR / "node_modules" / "openwiki" / "package.json").exists():
        return False, "openwiki CLI 依赖未安装 (agents/openwiki 需 npm install)"
    return True, f"openwiki CLI 可用 ({OPENWIKI_DIR})"


def query(question: str, timeout: float = 300) -> tuple[bool, str]:
    """向本地知识脑提一个问题, 返回 (ok, reply_or_err)."""
    if not question.strip():
        return False, "问题不能为空"
    ok_b, detail = _cli_ok()
    if not ok_b:
        return False, detail
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not npx:
        return False, "找不到 npx，请确认已安装 Node.js，并将其加入系统 PATH"
    cmd = [npx, "--no-install", "openwiki", "personal", question]
    try:
        proc = subprocess.run(
            cmd, cwd=str(OPENWIKI_DIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=int(timeout),
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except subprocess.TimeoutExpired:
        return False, f"openwiki 执行超时 ({int(timeout)} 秒)"
    except PermissionError as e:
        return False, f"openwiki 权限错误: {e}"
    except OSError as e:
        return False, f"openwiki 启动失败: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"openwiki 执行异常: {e}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, f"openwiki 退出码 {proc.returncode}: {err[-500:]}"
    reply = _strip_banner(proc.stdout or "")
    if not reply:
        return False, "openwiki 无输出"
    return True, reply
