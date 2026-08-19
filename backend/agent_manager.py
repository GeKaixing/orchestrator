"""AgentManager — 托管三个 agent worker 进程, 写穿 db agents 表.

- start(name): spawn `python -m recruit.agents.worker <name> --port 0`, 读上报端口, 记 {status,pid,port}.
- stop(name): 按平台停止进程树, 清状态.
- 后台健康轮询线程: 每 ~3s 对 running worker TCP health → 更新 status/detail/last_health;
  连续 N 次失败自动 restart.
- status_all(): 合并 db 状态与当前进程存活性, 供 /api/agents.

worker stderr 落到 logs/agents/<name>.log, 避免管道缓冲阻塞 worker.
"""

from __future__ import annotations

import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from recruit import get_logger
from recruit import platform
from recruit.agents import client as agent_client
from recruit.paths import WORK_DIR
from recruit.services import db

log = get_logger("agent_manager")

# 知识问答统一走 openwiki agent (Personal 模式本地知识脑), 与 wechat/shop 同为 worker 进程
AGENT_NAMES = ("wechat", "shop", "rag", "openwiki")
POLL_INTERVAL = 3
MAX_CONSECUTIVE_FAIL = 3
LOG_DIR = WORK_DIR / "logs" / "agents"


def _auto_start_names() -> list[str]:
    """后端启动时自动拉起的 agent 名单.

    默认排除 rag: rag 服务 (localhost:2024) 尚未部署, 拉起只会 degraded.
    部署后可设环境变量 RECRUIT_SKIP_AGENTS= (空) 或 RECRUIT_SKIP_AGENTS= 来启用.
    """
    skip = {s.strip() for s in os.environ.get("RECRUIT_SKIP_AGENTS", "rag").split(",") if s.strip()}
    return [n for n in AGENT_NAMES if n not in skip]


def _kill_tree(pid: int) -> None:
    platform.kill_process_tree(pid)


class AgentManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen | None] = {n: None for n in AGENT_NAMES}
        self._poll_thread: threading.Thread | None = None
        self._stopped = False
        self._consecutive_fail: dict[str, int] = {}

    # ── lifecycle ────────────────────────────────────────────
    def start(self, name: str) -> dict:
        if name not in AGENT_NAMES:
            return {"ok": False, "error": f"未知 agent: {name}"}
        with self._lock:
            proc = self._procs.get(name)
            if proc is not None and proc.poll() is None:
                return {"ok": True, "pid": proc.pid, "msg": f"{name} 已在运行"}
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            err_log = open(LOG_DIR / f"{name}.log", "a", encoding="utf-8", errors="replace")
            proc = subprocess.Popen(
                [sys.executable, "-m", "recruit.agents.worker", name, "--port", "0"],
                cwd=str(WORK_DIR),
                stdout=subprocess.PIPE, stderr=err_log,
                text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
                **platform.popen_kwargs(),
            )
        except Exception as e:  # noqa: BLE001
            db.upsert_agent(name, status="error", pid=None, port=None, detail=f"启动异常: {e}")
            return {"ok": False, "error": f"启动失败: {e}"}

        port = self._read_port(proc, name)
        with self._lock:
            self._procs[name] = proc
        if port is None:
            db.upsert_agent(name, status="error", pid=proc.pid, port=None,
                            detail="worker 未上报端口 (启动失败?)")
            return {"ok": False, "error": f"{name} worker 未上报端口"}
        db.upsert_agent(name, status="running", pid=proc.pid, port=port, detail="worker 运行中")
        log.info("agent %s 已启动 pid=%s port=%s", name, proc.pid, port)
        return {"ok": True, "pid": proc.pid, "port": port}

    def _read_port(self, proc: subprocess.Popen, name: str, timeout: float = 20) -> int | None:
        """在 timeout 秒内等待 worker 输出 'PORT <port>' 行.

        使用后台线程 + queue 实现非阻塞读取, 避免 readline() 无限阻塞.
        """
        result_q: queue.Queue[int | None] = queue.Queue()

        def _reader() -> None:
            """后台线程: 逐行读 stdout, 找到 PORT 行后放入 result_q."""
            try:
                while True:
                    raw_line = proc.stdout.readline()
                    if not raw_line:
                        # stdout 关闭 (worker 已退出), 没有 PORT 行
                        result_q.put(None)
                        return
                    line = raw_line.strip()
                    if line.startswith("PORT "):
                        try:
                            result_q.put(int(line.split()[1]))
                        except (ValueError, IndexError):
                            result_q.put(None)
                        return
            except Exception:  # noqa: BLE001
                result_q.put(None)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        try:
            return result_q.get(timeout=timeout)
        except queue.Empty:
            # 超时: worker 既不输出 PORT 也不退出 → 终止进程
            log.warning("agent %s: 等待 PORT 超时, 终止 worker (pid=%s)", name, proc.pid)
            _kill_tree(proc.pid)
            # 等待进程真正退出
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
            return None

    def stop(self, name: str) -> dict:
        with self._lock:
            proc = self._procs.get(name)
        if proc is not None and proc.poll() is None:
            _kill_tree(proc.pid)
            # 等待进程真正退出 (Windows 释放 .pyd/.dll 句柄需要时间)
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
        with self._lock:
            self._procs[name] = None
        self._consecutive_fail[name] = 0
        db.upsert_agent(name, status="stopped", pid=None, port=None, detail="")
        log.info("agent %s 已停止", name)
        return {"ok": True}

    def restart(self, name: str) -> dict:
        self.stop(name)
        time.sleep(0.3)
        return self.start(name)

    def start_all(self) -> None:
        db.init_db()
        self._reconcile()
        for name in _auto_start_names():
            self.start(name)
        self._start_poller()

    def stop_all(self) -> None:
        self._stopped = True
        for name in list(self._procs):
            self.stop(name)

    def _reconcile(self) -> None:
        """清 stale running 行 (connect 探活失败 → stopped), 保证下次 start 干净."""
        for row in db.get_agents():
            if row.get("status") == "running" and row.get("port"):
                try:
                    agent_client.tcp_request(row["port"], "health", timeout=2)
                except Exception:  # noqa: BLE001
                    log.info("清理 stale agent 行: %s", row["name"])
                    db.upsert_agent(row["name"], status="stopped", pid=None, port=None,
                                    detail="stale(进程已退出)")

    # ── health polling ───────────────────────────────────────
    def _start_poller(self) -> None:
        if self._poll_thread is None or not self._poll_thread.is_alive():
            self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._poll_thread.start()

    def _poll_loop(self) -> None:
        while not self._stopped:
            try:
                self._poll_once()
            except Exception as e:  # noqa: BLE001
                log.error("健康轮询异常: %s", e)
            time.sleep(POLL_INTERVAL)

    def _poll_once(self) -> None:
        with self._lock:
            procs = list(self._procs.items())
        for name, proc in procs:
            if proc is None:
                continue
            if proc.poll() is not None:
                # 进程已退出 → 自动重启
                log.warning("agent %s 进程已退出 (code=%s), 自动重启", name, proc.returncode)
                self._consecutive_fail[name] = 0
                self.restart(name)
            else:
                self._health_check(name)

    def _health_check(self, name: str) -> None:
        row = db.get_agent(name) or {}
        port = row.get("port")
        if not port:
            return
        checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            h = agent_client.tcp_request(port, "health", timeout=20)
            ok = bool(h.get("ok"))
            detail = h.get("detail", "")
            status = "running" if ok else "degraded"
            self._consecutive_fail[name] = 0
            db.upsert_agent(name, status=status, detail=detail,
                            last_health=h.get("checked_at") or checked_at)
        except socket.timeout:
            # worker 忙 (正在跑长动作) 或健康检查本身慢 → 降级, 不重启
            self._consecutive_fail[name] = 0
            db.upsert_agent(name, status="degraded",
                            detail="health 超时 (worker 忙或检查慢)", last_health=checked_at)
        except Exception as e:  # noqa: BLE001
            # 连接被拒等 → worker 可能已死, 累计失败到阈值自动重启
            fails = self._consecutive_fail.get(name, 0) + 1
            self._consecutive_fail[name] = fails
            db.upsert_agent(name, status="error", detail=f"health 失败: {e}",
                            last_health=checked_at)
            if fails >= MAX_CONSECUTIVE_FAIL:
                log.warning("agent %s 连续 %d 次 health 失败, 自动重启", name, fails)
                self._consecutive_fail[name] = 0
                self.restart(name)

    # ── status ───────────────────────────────────────────────
    def status_all(self) -> list[dict]:
        db.init_db()
        rows = {r["name"]: r for r in db.get_agents()}
        out: list[dict] = []
        with self._lock:
            alive = {n: (p is not None and p.poll() is None) for n, p in self._procs.items()}
        for name in AGENT_NAMES:
            row = rows.get(name) or db.upsert_agent(name, status="stopped")
            status = row["status"]
            if status == "running" and not alive.get(name, False):
                status = "stopped"
                db.upsert_agent(name, status="stopped", pid=None, port=None, detail="进程已退出")
                row["status"] = status
            out.append(row)
        return out


manager = AgentManager()
