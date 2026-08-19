"""子 Agent 下载 — 把依赖项目 (微信 / 微信小店) git clone 到 agents/ 目录, 支持更新/移除.

依赖项目被 orchestrator 通过 recruit.paths._sibling() 解析 (优先 orchestrator/agents/<name>),
所以克隆到 agents/ 下即可被识别; 本模块是目标机上「缺依赖时一键拉取」的入口.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

from recruit import get_logger
from recruit import platform
from recruit.paths import PROJECT_ROOT

log = get_logger("agent_store")


def _resolve_exe(name: str) -> str | None:
    """按当前平台解析可执行文件完整路径 (Windows 下 npm 需 npm.cmd)。"""
    return platform.resolve_executable(name)


def _check_git() -> tuple[bool, str]:
    """检查 git 是否可用."""
    if _resolve_exe("git"):
        return True, ""
    return False, "未找到 git，请安装 Git 并加入系统 PATH"


def _check_npm() -> tuple[bool, str]:
    """检查 npm 是否可用."""
    if _resolve_exe("npm"):
        return True, ""
    return False, "未找到 npm，请安装 Node.js 并加入系统 PATH"

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
    git = _resolve_exe("git")
    if not git:
        raise FileNotFoundError("未找到 git，请安装 Git 并加入系统 PATH")
    return subprocess.run(
        [git, "-C", str(p), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def _kill_processes_under(p: Path, timeout: int = 30) -> list[int]:
    """杀掉与目录 p 绑定的进程, 释放被锁的文件 (.log / .pyd / .dll 等).

    旧逻辑只杀「可执行文件在 p 内」的进程 (.venv/Scripts/python.exe), 但 worker 往往
    从 orchestrator/.venv 或 uv 目录启动, exe 不在 p 内, 却能打开 agents/<name>/logs/*.log
    并一直持有句柄 -> 旧逻辑杀不到, rmtree 报 [WinError 32] 进程无法访问.

    这里优先用 psutil 按三类信号精准猎杀 (任一满足即杀, 但排除自身与 API 主进程):
      * 持有打开的文件句柄位于 p 内 (最关键: 直接定位锁持有者);
      * 当前工作目录 (cwd) 在 p 内 (进程从目录内运行, 可能随后打开文件);
      * (保留) 可执行文件位于 p 内.
    无 psutil 时退回 wmic 的 exe 前缀逻辑. 返回被杀 pid 列表; 失败返回 [].
    """
    if os.name != "nt":
        return []
    prefix = str(p).lower().rstrip("\\") + "\\"
    self_pid = os.getpid()

    def _is_api_server(cl: str) -> bool:
        low = cl.lower()
        return any(t in low for t in ("uvicorn", "app:app", "backend.app",
                                      "backend\\app.py", "-m backend", "run_desktop"))

    try:
        import psutil  # 可能被 import 失败的环境
    except Exception:  # noqa: BLE001
        psutil = None

    if psutil is not None:
        killed: list[int] = []
        # 只有这些运行时进程才可能持有 agent 目录下的文件 (.log/.pyd/.dll),
        # 限制 open_files() 探测范围, 避免逐个扫描 svchost 等系统进程、以及句柄极多的
        # electron 进程导致卡顿. (锁通常由 python/node 写的 worker 持有, 不会是 electron)
        _PROBE_NAMES = {"python.exe", "python3.exe", "pythonw.exe", "node.exe"}
        for proc in psutil.process_iter(["pid", "name", "exe", "cwd", "cmdline"]):
            try:
                pid = int(proc.info["pid"])
                if pid == self_pid:
                    continue
                cl = " ".join(proc.info.get("cmdline") or [])
                if _is_api_server(cl):  # 绝对不杀 API 主进程
                    continue
                exe = (proc.info.get("exe") or "").lower()
                cwd = ""
                try:
                    cwd = (proc.info.get("cwd") or "").lower()
                except Exception:  # noqa: BLE001
                    cwd = ""
                hit = exe.startswith(prefix) or cwd.startswith(prefix)
                if not hit:
                    # 仅对可能持有 agent 文件的运行时进程探测打开的句柄, 避免逐个扫描
                    # svchost 等系统进程导致卡顿 (worker 多为 python/node/electron).
                    if (proc.info.get("name") or "").lower() in _PROBE_NAMES:
                        try:
                            for f in proc.open_files():
                                if f.path.lower().startswith(prefix):
                                    hit = True
                                    break
                        except Exception:  # noqa: BLE001
                            pass
                if hit:
                    try:
                        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                                       capture_output=True, timeout=timeout)
                        killed.append(pid)
                    except Exception:  # noqa: BLE001
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):  # noqa: BLE001
                continue
        return killed

    # fallback: 仅按 exe 前缀过滤 (无 psutil)
    killed = []
    try:
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
    for ln in lines[1:]:
        cols = [c.strip() for c in ln.split(",")]
        if len(cols) <= max(pid_idx, path_idx):
            continue
        pid_s, path = cols[pid_idx], cols[path_idx]
        if not pid_s.isdigit() or not path:
            continue
        if int(pid_s) == self_pid:
            continue
        if path.lower().startswith(prefix):
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", pid_s],
                               capture_output=True, timeout=timeout)
                killed.append(int(pid_s))
            except Exception:  # noqa: BLE001
                pass
    return killed


# Windows 保留设备名: 任何以这些名字命名的真实文件/目录, Win32 的 DeleteFile/
# RemoveDirectory 都会失败 (被当成 NUL/CON... 设备, 报 [WinError 5] 拒绝访问),
# 且现代 Windows 默认关闭 8.3 短名, 也没有可用的短名可绕过. 只能通过 "相对父目录
# 句柄" 的 NT 调用绕过保留名检查来删除 (见 _delete_reserved_name).
_RESERVED_NAMES = (
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def _delete_reserved_name(path: Path) -> bool:
    """尽力删除一个名字命中 Windows 保留设备名 (nul/con/prn/aux/com1-9/lpt1-9) 的
    真实文件/目录. 普通 DeleteFile/RemoveDirectory 会因 [WinError 5] 失败; 这里打开
    *父目录* 句柄, 用 ntdll.NtOpenFile 相对该句柄打开目标, 再标记删除-on-close.
    成功返回 True, 否则返回 False (调用方再退回 "移走目录" 方案). 仅 Windows 生效.
    """
    if os.name != "nt":
        return False
    if path.name.lower() not in _RESERVED_NAMES:
        return False
    try:
        import ctypes
        from ctypes import (wintypes, Structure, POINTER, byref, c_void_p,
                            c_ulong, c_ushort, c_wchar)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

        class _US(Structure):
            _fields_ = [("Length", c_ushort), ("MaximumLength", c_ushort),
                        ("Buffer", POINTER(c_wchar))]

        class _OA(Structure):
            _fields_ = [("Length", c_ulong), ("RootDirectory", wintypes.HANDLE),
                        ("ObjectName", POINTER(_US)), ("Attributes", c_ulong),
                        ("SecurityDescriptor", c_void_p),
                        ("SecurityQualityOfService", c_void_p)]

        NtOpenFile = ntdll.NtOpenFile
        NtOpenFile.argtypes = [POINTER(wintypes.HANDLE), c_ulong, POINTER(_OA),
                               c_void_p, c_ulong, c_ulong]
        NtOpenFile.restype = ctypes.c_long
        NtSetInformationFile = ntdll.NtSetInformationFile
        NtSetInformationFile.argtypes = [wintypes.HANDLE, c_void_p, c_void_p,
                                        c_ulong, c_ulong]
        NtSetInformationFile.restype = ctypes.c_long
        NtClose = ntdll.NtClose
        NtClose.argtypes = [wintypes.HANDLE]
        NtClose.restype = ctypes.c_long

        parent = str(path.parent)
        # 打开父目录句柄: SYNCHRONIZE|FILE_READ_ATTRIBUTES|FILE_DELETE_CHILD|FILE_LIST_DIRECTORY,
        # FILE_FLAG_BACKUP_SEMANTICS 允许打开目录, FILE_FLAG_OPEN_REPARSE_POINT 避免跟随链接.
        h_parent = kernel32.CreateFileW(
            parent, 0x100000 | 0x80 | 0x10 | 0x1, 0x1 | 0x2 | 0x4, None, 3,
            0x2000000 | 0x200000, None)
        if h_parent == wintypes.HANDLE(-1).value:
            return False
        name = path.name
        buf = ctypes.create_unicode_buffer(name)
        us = _US()
        us.Length = len(name) * 2
        us.MaximumLength = ctypes.sizeof(buf)
        us.Buffer = ctypes.cast(buf, POINTER(c_wchar))
        us._keep = buf
        oa = _OA()
        oa.Length = ctypes.sizeof(_OA)
        oa.RootDirectory = wintypes.HANDLE(h_parent)
        oa.ObjectName = ctypes.pointer(us)
        oa.Attributes = 0x40  # OBJ_CASE_INSENSITIVE
        h_file = wintypes.HANDLE()
        iosb = (ctypes.c_ulong * 2)()
        status = NtOpenFile(byref(h_file), 0x10000, byref(oa), byref(iosb),
                            0x1 | 0x2 | 0x4, 0)  # DELETE
        if status != 0:
            kernel32.CloseHandle(h_parent)
            return False
        # FileDispositionInfo (0x0D): 标记删除, 关闭句柄时真正删除.
        disp = ctypes.c_ubyte(1)
        st = NtSetInformationFile(h_file, byref(iosb), byref(disp), 1, 0x0D)
        NtClose(h_file)
        kernel32.CloseHandle(h_parent)
        return st == 0
    except Exception:  # noqa: BLE001
        return False


def _move_aside(p: Path) -> Path | None:
    """把目录改名为 `<name>.removed-<时间戳>`, 使其脱离 agents/<name> 激活位置.
    重命名只改顶层目录自身条目, 不会按名打开内部保留名/被锁文件, 因此总能成功.
    返回新路径; 若全部失败返回 None.
    """
    parent = p.parent
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for i in range(0, 100):
        suffix = "" if i == 0 else f"-{i}"
        dest = parent / f"{p.name}.removed-{stamp}{suffix}"
        try:
            p.rename(dest)
            return dest
        except OSError:
            continue
    return None


def _clear_readonly(func, path, _exc_info) -> None:
    """rmtree 的 onerror: 先清只读位重试; 仍失败且命中 Windows 保留名时, 用 NT 相对
    父目录句柄删除 (绕过保留名检查). 都不行则原样抛出, 由 _rmtree_retry 的调用方退回移走方案."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    try:
        func(path)
    except OSError:
        if _delete_reserved_name(Path(path)):
            return
        raise


def _rmtree_retry(p: Path, attempts: int = 8) -> None:
    """Windows 下 .pyd/.dll 被进程占用 / 含 Windows 保留名文件时 rmtree 失败, 逐步加大间隔重试."""
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
    # Check git availability
    ok_git, err_git = _check_git()
    if not ok_git:
        return {"ok": False, "error": err_git}
    git_exe = _resolve_exe("git")
    try:
        proc = subprocess.run(
            [git_exe, "clone", "--depth", "1", a["repo"], str(p)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=CLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(p, ignore_errors=True)
        return {"ok": False, "error": f"git clone 超时 ({CLONE_TIMEOUT}s)"}
    except (FileNotFoundError, OSError) as e:
        return {"ok": False, "error": f"找不到 git 可执行文件: {e}"}
    if proc.returncode != 0:
        shutil.rmtree(p, ignore_errors=True)
        return {"ok": False, "error": proc.stderr.strip() or "git clone 失败"}
    # Node 子项目 (openwiki): clone 后装依赖
    if a.get("node") and (p / "package.json").exists():
        ok_npm, err_npm = _check_npm()
        if not ok_npm:
            return {"ok": False, "error": err_npm}
        npm_exe = _resolve_exe("npm")
        try:
            np = subprocess.run(
                [npm_exe, "install", "--no-audit", "--no-fund"],
                cwd=str(p), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=CLONE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "npm install 超时", "path": str(p)}
        except (FileNotFoundError, OSError) as e:
            return {"ok": False, "error": f"找不到 npm 可执行文件: {e}", "path": str(p)}
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

    ok_git, err_git = _check_git()
    if not ok_git:
        return {"ok": False, "error": err_git}
    try:
        proc = _git(p, "pull", "--ff-only")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"git pull 超时 ({CLONE_TIMEOUT}s)"}
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or "git pull 失败"}
    if a.get("node") and (p / "package.json").exists():
        ok_npm, err_npm = _check_npm()
        if not ok_npm:
            return {"ok": False, "error": err_npm}
        try:
            npm_exe = _resolve_exe("npm")
            np = subprocess.run(
                [npm_exe, "install", "--no-audit", "--no-fund"],
                cwd=str(p), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=CLONE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "npm install 超时", "path": str(p)}
        except (FileNotFoundError, OSError) as e:
            return {"ok": False, "error": f"找不到 npm 可执行文件: {e}", "path": str(p)}
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
    try:
        _rmtree_retry(p)
        log.info("已移除 %s -> %s", a["key"], p)
        return {"ok": True, "path": str(p)}
    except OSError as e:
        # 仍删不掉 (含 Windows 保留名文件如 nul, 或 .pyd/.dll / .log 仍被锁):
        # 失败前再杀一次 (worker 可能刚被重生并重新打开文件), 然后整目录改名移走,
        # 使其脱离 agents/<name> 激活位置, 避免在 UI 反复 409. 用户稍后可在管理员/WSL 下手动彻底删除.
        _kill_processes_under(p)
        time.sleep(0.5)
        moved = _move_aside(p)
        if moved:
            log.warning("rmtree 失败(%s): 已将 %s 移至 %s", e, p, moved)
            return {"ok": True, "path": str(moved),
                    "warning": f"无法用普通方式删除(可能含 Windows 保留名文件如 nul, "
                               f"或 .pyd/.dll 仍被占用): 已将目录改名为 {moved.name}，"
                               f"可稍后在管理员命令行 / WSL 下手动彻底删除"}
        raise
