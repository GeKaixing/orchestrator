"""子 Agent 下载 — 把依赖项目 (微信 / 微信小店) git clone 到 agents/ 目录, 支持更新/移除.

依赖项目被 orchestrator 通过 recruit.paths._sibling() 解析 (优先 orchestrator/agents/<name>),
所以克隆到 agents/ 下即可被识别; 本模块是目标机上「缺依赖时一键拉取」的入口.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

from recruit import get_logger
from recruit.paths import PROJECT_ROOT

log = get_logger("agent_store")

# 可下载的子 agent 注册表; dir 需匹配 recruit/paths._sibling 查找的项目名
AGENTS = [
    {
        "key": "wxshop-cli",
        "name": "微信小店",
        "description": "微信小店 CLI (Playwright): 扫描达人 / 提取联系方式 / IM 招商",
        "repo": "https://github.com/GeKaixing/wxshop-cli",
        "dir": "wxshop-cli",
    },
    {
        "key": "wechat-friend-add",
        "name": "微信",
        "description": "微信桌面端加好友 / 发消息 (固定坐标自动化)",
        "repo": "https://github.com/GeKaixing/wechat-friend-add.git",
        "dir": "wechat-friend-add",
    },
    {
        "key": "openwiki",
        "name": "知识库 (OpenWiki)",
        "description": "OpenWiki 个人知识脑 CLI (Node): npx openwiki personal 问答, 知识库 ~/.openwiki/wiki",
        "repo": "https://github.com/GeKaixing/openwiki.git",
        "dir": "openwiki",
        "node": True,
    },
    {
        "key": "wiki",
        "name": "知识源 (wiki)",
        "description": "有机地标领域 wiki (OKF 风格, markdown 在根 + entities/concepts), openwiki 知识脑的数据源",
        "repo": "https://github.com/GeKaixing/wiki.git",
        "dir": "wiki",
    },
]

AGENTS_DIR = PROJECT_ROOT / "agents"
CLONE_TIMEOUT = 180


def _get(key: str) -> dict:
    for a in AGENTS:
        if a["key"] == key:
            return a
    raise KeyError(f"未知子 agent: {key} (可选: {', '.join(a['key'] for a in AGENTS)})")


def _target(a: dict) -> Path:
    return AGENTS_DIR / a["dir"]


def _git(p: Path, *args: str, timeout: int = CLONE_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(p), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def _kill_processes_under(p: Path, timeout: int = 30) -> list[int]:
    """杀掉可执行文件位于项目目录 p 内的进程 (如 .venv/Scripts/python.exe).

    这些进程会把 .pyd/.dll 锁住, 导致 rmtree 报 [WinError 5] 拒绝访问.
    返回被杀掉的 pid 列表. 非 Windows 或无 wmic 时返回 [] (不视为错误).
    """
    if os.name != "nt":
        return []
    killed: list[int] = []
    try:
        # 不带 WHERE: wmic 的 LIKE 无法匹配带反斜杠的路径 (Win10 无效查询),
        # 改为全量枚举后在本进程内按前缀过滤.
        res = subprocess.run(
            ["wmic", "process", "get", "ProcessId,ExecutablePath", "/format:csv"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001
        return []
    lines = [ln for ln in (res.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().lower() for h in lines[0].split(",")]
    try:
        pid_idx = header.index("processid")
        path_idx = header.index("executablepath")
    except ValueError:
        return []
    prefix = str(p).lower()
    for ln in lines[1:]:
        cols = [c.strip() for c in ln.split(",")]
        if len(cols) <= max(pid_idx, path_idx):
            continue
        pid_s, path = cols[pid_idx], cols[path_idx]
        if not pid_s.isdigit() or not path:
            continue
        if int(pid_s) == os.getpid():  # 别杀自己
            continue
        if path.lower().startswith(prefix):
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", pid_s],
                               capture_output=True, timeout=timeout)
                killed.append(int(pid_s))
            except Exception:  # noqa: BLE001
                pass
    return killed


def _rmtree_retry(p: Path, attempts: int = 8) -> None:
    """Windows 下 .pyd/.dll 被进程占用时 rmtree 失败, 逐步加大间隔重试."""
    def _clear_readonly(func, path, _exc_info) -> None:
        """Git pack files can be read-only on Windows; clear that attribute and retry."""
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
        func(path)

    for i in range(attempts):
        try:
            shutil.rmtree(p, onerror=_clear_readonly)
            return
        except OSError:
            if i == attempts - 1:
                raise
            # 前几次短等, 后面逐步拉长 (0.5→0.5→1→1→2→2→3)
            time.sleep(0.5 if i < 2 else (i if i < 6 else 3))


def list_agents() -> list[dict]:
    out: list[dict] = []
    for a in AGENTS:
        p = _target(a)
        entry: dict = {**a, "installed": p.exists(), "git": (p / ".git").exists()}
        # 对 Node 子项目来说，仓库存在不等于 CLI 可用；还必须完成 npm 依赖安装。
        entry["ready"] = bool(entry["installed"] and (not a.get("node") or
            (p / "node_modules" / "openwiki" / "package.json").exists()))
        if entry["git"]:
            try:
                head = _git(p, "rev-parse", "--short", "HEAD", timeout=10)
                branch = _git(p, "rev-parse", "--abbrev-ref", "HEAD", timeout=10)
                entry["branch"] = branch.stdout.strip() or "?"
                entry["head"] = head.stdout.strip() or ""
            except Exception:  # noqa: BLE001
                entry["branch"] = "?"
                entry["head"] = ""
        out.append(entry)
    return out


def install(key: str) -> dict:
    a = _get(key)
    p = _target(a)
    if p.exists():
        if (p / ".git").exists():
            return {"ok": False, "error": f"{a['dir']} 已安装, 不能覆盖"}
        # 目录存在但非 git 残留 (上次 remove 未清干净), 先尝试清理
        try:
            _kill_processes_under(p)
            time.sleep(0.5)
            _rmtree_retry(p)
            log.info("已清理残留目录 %s", p)
        except OSError as e:
            return {"ok": False, "error": f"{a['dir']} 已存在且无法删除 (非 git): {e}"}
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", a["repo"], str(p)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=CLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(p, ignore_errors=True)
        return {"ok": False, "error": f"git clone 超时 ({CLONE_TIMEOUT}s)"}
    if proc.returncode != 0:
        shutil.rmtree(p, ignore_errors=True)
        return {"ok": False, "error": proc.stderr.strip() or "git clone 失败"}
    # Node 子项目 (openwiki): clone 后装依赖
    if a.get("node") and (p / "package.json").exists():
        try:
            np = subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=str(p), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=CLONE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "npm install 超时", "path": str(p)}
        if np.returncode != 0:
            return {"ok": False, "error": np.stderr.strip()[-500:] or "npm install 失败",
                    "path": str(p)}
    log.info("已下载 %s -> %s", a["key"], p)
    return {"ok": True, "path": str(p)}


def update(key: str) -> dict:
    a = _get(key)
    p = _target(a)
    if not p.is_dir():
        return {"ok": False, "error": f"{a['dir']} 未安装"}
    if not (p / ".git").exists():
        return {"ok": False, "error": f"{p} 不是 git 仓库, 无法更新"}
    try:
        proc = _git(p, "pull", "--ff-only")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"git pull 超时 ({CLONE_TIMEOUT}s)"}
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or "git pull 失败"}
    if a.get("node") and (p / "package.json").exists():
        try:
            np = subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=str(p), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=CLONE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "npm install 超时", "path": str(p)}
        if np.returncode != 0:
            return {"ok": False, "error": np.stderr.strip()[-500:] or "npm install 失败",
                    "path": str(p)}
    log.info("已更新 %s", a["key"])
    return {"ok": True, "detail": proc.stdout.strip()}


def remove(key: str) -> dict:
    a = _get(key)
    p = _target(a)
    if not p.exists():
        return {"ok": False, "error": f"{a['dir']} 未安装"}
    # 先杀掉占用 .venv 里 .pyd/.dll 的进程 (正在跑的 run/孤立进程), 再删目录
    killed = _kill_processes_under(p)
    if killed:
        log.info("已终止 %d 个占用 %s 的进程: %s", len(killed), a["dir"], killed)
        time.sleep(1.0)  # 等 Windows 释放文件句柄
    _rmtree_retry(p)
    log.info("已移除 %s -> %s", a["key"], p)
    return {"ok": True, "path": str(p)}
