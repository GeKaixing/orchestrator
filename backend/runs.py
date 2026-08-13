"""RunManager — 以子进程跑编排 CLI, 记录运行与日志到 SQLite.

- 同一时刻只允许一个运行中 run.
- 启动: [sys.executable, "-m", "recruit", "--stage", ...] (cwd=orchestrator).
- 日志: reader 线程逐行 stdout/stderr → insert_log.
- 停止: taskkill /T /F 杀进程树; 线程随 stdout 关闭结束.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Any

from recruit.paths import WORK_DIR
from recruit.services import db

CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0

STAGES = ("all", "scan", "add", "send", "im")


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._run_id: int | None = None
        self._stopped = False

    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, payload: dict) -> dict:
        run_type = (payload.get("type") or "recruit").strip().lower()
        if run_type == "reply":
            cmd = [sys.executable, "-m", "recruit", "--stage", "reply"]
            stage = "reply"
            limit = None
        else:
            if run_type != "recruit":
                run_type = "recruit"
            stage = (payload.get("stage") or "all").strip() or "all"
            if stage not in STAGES:
                return {"error": f"非法 stage: {stage}"}
            limit = int(payload.get("limit") or 10)
            cmd = [sys.executable, "-m", "recruit", "--stage", stage,
                   "--limit", str(limit), "--max-pages", str(int(payload.get("max_pages") or 1))]
            for key, flag in (("cat", "--cat"), ("contacts", "--contacts")):
                if payload.get(key):
                    cmd += [flag, str(payload[key])]
            if payload.get("text"):
                cmd += ["--text", str(payload["text"])]

        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return {"error": "已有任务在运行"}
            self._stopped = False

        run_id = db.insert_run(run_type, stage, limit, summary=" ".join(cmd))
        proc = subprocess.Popen(
            cmd, cwd=str(WORK_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NEW_PROCESS_GROUP,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        with self._lock:
            self._proc = proc
            self._run_id = run_id
        threading.Thread(target=self._reader, args=(proc, run_id), daemon=True).start()
        return {"id": run_id, "cmd": " ".join(cmd)}

    def _reader(self, proc: subprocess.Popen, run_id: int) -> None:
        for line in iter(proc.stdout.readline, ""):  # type: ignore[union-attr]
            line = line.rstrip("\r\n")
            if line:
                db.insert_log(run_id, line)
        proc.wait()
        code = proc.returncode
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._proc = None
            self._run_id = None
            stopped = self._stopped
        status = "stopped" if stopped else ("finished" if code == 0 else "failed")
        db.update_run(run_id, status=status, exit_code=code, finished_at=now)

    def stop(self, run_id: int) -> dict:
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            self._stopped = True
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                   capture_output=True, timeout=30)
                else:
                    proc.terminate()
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            db.update_run(run_id, status="stopped")
        return {"ok": True}


manager = RunManager()
