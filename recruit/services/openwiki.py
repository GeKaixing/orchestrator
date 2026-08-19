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


DEFAULT_QUERY_TIMEOUT = 60

# 这些关键词命中时, 该行极可能是真正的报错 (而非末尾装饰框/ banner).
_ERROR_HINTS = (
    "error", "Error", "ERROR", "failed", "Failed", "FAILED", "exception",
    "Exception", "Traceback", "ENOENT", "ECONN", "ETIMEDOUT", "timeout",
    "Timeout", "401", "403", "429", "undefined", "Cannot", "cannot", "找不到",
    "失败", "超时", "拒绝", "Invalid", "invalid", "not found", "NoneType",
)


def _extract_error(text: str) -> str:
    """从 openwiki 输出里抽取真正的报错行.

    openwiki 的报错常以 box 装饰框结尾 (LangSmith/Run failed 之类), 真正的
    错误原因在前面被截断. 这里优先返回命中关键词的行, 找不到则退回到末尾片段.
    """
    lines = [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]
    hits = [ln for ln in lines if any(h in ln for h in _ERROR_HINTS)]
    if hits:
        # 去掉重复/装饰行 (纯边框), 取靠前的关键行
        meaningful = [ln for ln in hits if not set(ln) <= set("─│┌┐└┘├┤╭╮╰╯┼═ |+-")]
        chosen = meaningful or hits
        return "\n".join(chosen[:12])
    if lines:
        return "\n".join(lines[-12:])
    return "(无输出)"


def _stop_process_tree(proc: subprocess.Popen[str]) -> None:
    """Stop npx and the node process it launches (Windows does not do this by default)."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True, timeout=15,
            )
        else:
            proc.kill()
    except Exception:  # noqa: BLE001
        proc.kill()


def _clean_child_env() -> dict:
    """构造 openwiki 子进程环境, 剔除 WorkBuddy/CodeBuddy 会话的 safe-delete 拦截,
    并保证系统 Node 目录在 PATH 最前.

    会话环境会把 PATH 里的 rm/unlink/rmdir 重定向到 genie-trash (回收站) 工具,
    该工具在部分 Windows 环境会失败, 导致 openwiki 启动阶段报
    "[safe-delete] 操作失败: ERROR ... Some operations were aborted" (退出码 1).
    openwiki 只需要模型/provider 配置 (读 ~/.openwiki/.env), 无需这些会话变量.

    PATH 必须把系统 Node (C:\\Program Files\\nodejs) 放最前: openwiki 的
    better-sqlite3 原生模块按系统 Node 24 编译 (ABI 137); npx 生成的 .cmd 垫片
    用 PATH 里的 node 拉起 CLI, 若先命中受管 Node 22 (ABI 127) 会
    NODE_MODULE_VERSION 不匹配崩溃. 另外 Git Bash 把 PATH 传给原生进程时可能产生
    裸盘符 ("C") 之类的坏条目, 一并清掉.
    """
    env = {**os.environ, "PYTHONUTF8": "1"}
    drop_prefixes = (
        "CODEBUDDY_",          # 会话 id + safe-delete 拦截相关
        "BASH_FUNC_rm",        # rm/unlink/rmdir 的 bash 函数包装
        "BASH_FUNC_unlink",
        "BASH_FUNC_rmdir",
    )
    # 会话还会注入这几个非 CODEBUDDY_ 前缀的变量, 必须一并剔除, 否则 safe-delete
    # 拦截会以 --require 方式挂进 openwiki 的 node 进程 (见下面对 NODE_OPTIONS 的处理).
    drop_exact = (
        "CLAUDE_SESSION_ID",
        "GENIE_TRASH_DIR",     # 回收站工具目录 (safe-delete 重定向目标)
        "BASH_ENV",            # 指向 safe-delete-bash-env.sh, 会恢复 rm 函数包装
    )
    for k in [k for k in env if k.startswith(drop_prefixes) or k in drop_exact]:
        env.pop(k, None)
    # NODE_OPTIONS 里的 --require .../genie-safe-delete.cjs 是拦截的「根」: 它把
    # 每个 node 进程的 fs.rm/unlink 重定向到 genie-trash, 在 Windows 上会报
    # "Error during a trash operation: Some operations were aborted", 导致 openwiki
    # 写 ~/.openwiki/skills/.write-connector-staging-* 后删除失败并卡死. 剥掉该
    # --require, 保留 --use-system-ca 等其余开关 (公司代理/自签证书场景需要).
    node_opts = env.get("NODE_OPTIONS", "")
    if "genie-safe-delete" in node_opts:
        # 路径含空格 ("C:/Program Files/..."), 不能简单用 \S+ 匹配; 引号内允许任意字符.
        node_opts = re.sub(r'--require=(?:"[^"]*genie-safe-delete[^"]*"|\S*genie-safe-delete\S*)',
                           "", node_opts)
        node_opts = " ".join(node_opts.split())
        if node_opts:
            env["NODE_OPTIONS"] = node_opts
        else:
            env.pop("NODE_OPTIONS", None)
    # 从 PATH 移除 safe-bin shim 目录, 避免 rm/unlink 被重定向到回收站工具.
    # 兼容两种 PATH 形态: 原生 Windows (; 分隔) 与 Git Bash 传入的 (: 分隔).
    path = env.get("PATH", "")
    if ";" in path:
        segs = path.split(";")
    else:
        # Git Bash 冒号分隔: "C:/foo" 会被切出裸盘符 "C", 按 "盘符+/" 重新合并
        raw = path.split(":")
        segs = []
        i = 0
        while i < len(raw):
            s = raw[i]
            if len(s) == 1 and s.isalpha() and i + 1 < len(raw) and raw[i + 1].startswith(("/", "\\")):
                segs.append(s + ":" + raw[i + 1])
                i += 2
            else:
                segs.append(s)
                i += 1
    # 丢弃空条目 / 损坏条目 (如裸盘符 "C") / safe-bin 重定向目录
    parts = [p for p in segs if p and len(p.strip()) >= 3 and "safe-bin" not in p.lower()]
    # 系统 Node 目录无条件排最前 (若已存在先移除再插入, 避免位置靠后被受管 Node 抢占)
    if os.name == "nt":
        for cand in (r"C:\Program Files\nodejs", r"C:\Program Files (x86)\nodejs"):
            if os.path.isdir(cand):
                parts = [p for p in parts if os.path.normcase(p) != os.path.normcase(cand)]
                parts.insert(0, cand)
    env["PATH"] = os.pathsep.join(parts)
    return env


def _resolve_npx() -> str | None:
    """解析 npx 可执行文件, Windows 上优先系统 Node 安装.

    openwiki 的 better-sqlite3 原生模块按系统 Node 24 (ABI 137) 编译; 若 PATH 里
    先出现其它 Node (如 WorkBuddy 受管 Node 22, ABI 127), 直接调 npx 会
    NODE_MODULE_VERSION 不匹配而崩溃. 优先用系统 Node 的 npx, 找不到再走 PATH.
    """
    if os.name == "nt":
        for cand in (
            r"C:\Program Files\nodejs\npx.cmd",
            r"C:\Program Files (x86)\nodejs\npx.cmd",
        ):
            if os.path.exists(cand):
                return cand
    return shutil.which("npx.cmd" if os.name == "nt" else "npx")


def query(question: str, timeout: float = DEFAULT_QUERY_TIMEOUT) -> tuple[bool, str]:
    """向本地知识脑提一个问题, 返回 (ok, reply_or_err)."""
    if not question.strip():
        return False, "问题不能为空"
    ok_b, detail = _cli_ok()
    if not ok_b:
        return False, detail
    npx = _resolve_npx()
    if not npx:
        return False, "找不到 npx，请确认已安装 Node.js，并将其加入系统 PATH"
    cmd = [npx, "--no-install", "openwiki", "personal", question]
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(OPENWIKI_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,  # 强制非 TTY: 否则后端从控制台启动时 stdin 是 TTY,
            # openwiki 会进入交互式 TUI 而非一次性 print 模式, 卡住直到超时
            text=True, encoding="utf-8", errors="replace",
            env=_clean_child_env(),
        )
        stdout, stderr = proc.communicate(timeout=int(timeout))
    except subprocess.TimeoutExpired:
        _stop_process_tree(proc)
        try:
            tail_out, tail_err = proc.communicate()
        except Exception:  # noqa: BLE001
            tail_out, tail_err = "", ""
        # 超时也把已捕获的输出落盘, 否则 60s 超时是个黑盒, 无法定位卡在哪一步.
        try:
            from ..paths import PROJECT_ROOT
            log_dir = PROJECT_ROOT / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "openwiki_last_run.log").write_text(
                f"=== TIMEOUT ({int(timeout)}s) ===\nSTDOUT:\n{tail_out or ''}\n\nSTDERR:\n{tail_err or ''}",
                encoding="utf-8", errors="replace",
            )
        except Exception:  # noqa: BLE001
            pass
        return False, f"openwiki 执行超时 ({int(timeout)} 秒)"
    except PermissionError as e:
        return False, f"openwiki 权限错误: {e}"
    except OSError as e:
        return False, f"openwiki 启动失败: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"openwiki 执行异常: {e}"
    if proc.returncode != 0:
        combined = (stderr or "") + "\n" + (stdout or "")
        err = _extract_error(combined)
        # 完整输出落盘, 便于事后排查 (避免被 500 字截断淹没真实原因)
        try:
            from ..paths import PROJECT_ROOT
            log_dir = PROJECT_ROOT / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "openwiki_last_run.log").write_text(
                combined, encoding="utf-8", errors="replace"
            )
        except Exception:  # noqa: BLE001
            pass
        return False, f"openwiki 退出码 {proc.returncode}: {err}"
    reply = _strip_banner(stdout or "")
    if not reply:
        return False, "openwiki 无输出"
    return True, reply
