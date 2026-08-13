"""后台任务执行 — 以子进程跑编排 CLI.

设计: 启动 `python -m recruit ...`(或单体脚本) 作为独立子进程, GUI 不阻塞;
- reader 线程逐行读 stdout/stderr 推到 bridge 的 "log"
- poller 线程每 1s 轮询状态文件推到 bridge 的 "state"
- 停止 = taskkill /T /F 杀进程树 (Windows), 真正的可中断
- 进程结束推 "exit"(code) + "status"(idle)
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from .bridge import QueueBridge

CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0


def snapshot_state(state_file: Path) -> dict:
    """读 recruit_state.json 生成 {stats, rows} 快照."""
    rows: list[dict] = []
    data: dict = {}
    if state_file and state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    for key, st in data.items():
        rows.append({
            "wxid": key,
            "nickname": st.get("nickname") or "?",
            "stage": st.get("stage") or "pending",
            "reason": st.get("reason") or "",
            "updated": st.get("updated") or "",
        })
    stats: dict[str, int] = {}
    for r in rows:
        stats[r["stage"]] = stats.get(r["stage"], 0) + 1
    return {"stats": stats, "rows": rows}


class TaskWorker:
    """执行一个编排子进程; 同一时刻只跑一个任务."""

    def __init__(self, bridge: QueueBridge) -> None:
        self._bridge = bridge
        self._proc: subprocess.Popen | None = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, cmd: list[str], cwd: Path, state_file: Path,
              on_started: Callable[[int], None] | None = None) -> bool:
        """拉起子进程. 已在运行则返回 False."""
        if self.running:
            return False
        self._stop_evt.clear()
        self._bridge.push("status", {"state": "starting", "cmd": " ".join(cmd)})
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NEW_PROCESS_GROUP,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        with self._lock:
            self._proc = proc
        self._bridge.push("status",
                          {"state": "running", "cmd": " ".join(cmd), "pid": proc.pid})
        if on_started:
            on_started(proc.pid)
        threading.Thread(target=self._reader, args=(proc,), daemon=True).start()
        threading.Thread(target=self._poller, args=(proc, state_file), daemon=True).start()
        return True

    def _reader(self, proc: subprocess.Popen) -> None:
        for line in iter(proc.stdout.readline, ""):  # type: ignore[union-attr]
            line = line.rstrip("\r\n")
            if line:
                self._bridge.push("log", line)
        proc.wait()
        code = proc.returncode
        with self._lock:
            self._proc = None
        self._bridge.push("exit", code)
        self._bridge.push("status", {"state": "idle", "exit_code": code})

    def _poller(self, proc: subprocess.Popen, state_file: Path) -> None:
        while not self._stop_evt.is_set() and proc.poll() is None:
            time.sleep(1)
            self._bridge.push("state", snapshot_state(state_file))
        if not self._stop_evt.is_set():
            self._bridge.push("state", snapshot_state(state_file))

    def stop(self) -> None:
        """杀进程树并标记停止. 线程在 stdout 关闭后自行结束."""
        self._stop_evt.set()
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                        capture_output=True, timeout=30,
                    )
                else:
                    proc.terminate()
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        self._bridge.push("status", {"state": "stopping"})
