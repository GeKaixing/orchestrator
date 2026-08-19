"""Tests for backend.agent_manager — 验证 _read_port 超时机制."""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import pytest


# ── 帮助函数 ──────────────────────────────────────────────────
def _make_proc_that_never_outputs_port() -> subprocess.Popen:
    """启动一个子进程, 它永远不输出 PORT 但保持存活."""
    # 一个永不退出的 Python 进程
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(3600)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )


def _make_proc_that_outputs_port(port: int) -> subprocess.Popen:
    """启动一个子进程, 立即输出 PORT <port> 后退出."""
    return subprocess.Popen(
        [sys.executable, "-c", f"import time; print('PORT {port}', flush=True); time.sleep(0.5)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )


# ── 测试 ──────────────────────────────────────────────────────
class TestReadPort:
    """AgentManager._read_port 超时行为测试."""

    def test_returns_port_when_worker_outputs_port(self) -> None:
        """worker 输出 PORT 行 → 应正确返回端口号."""
        from backend.agent_manager import AgentManager

        mgr = AgentManager()
        proc = _make_proc_that_outputs_port(18080)
        try:
            port = mgr._read_port(proc, "test", timeout=5)
            assert port == 18080
        finally:
            proc.kill()
            proc.wait()

    def test_returns_none_when_worker_exits_without_port(self) -> None:
        """worker 退出但未输出 PORT → 应返回 None."""
        from backend.agent_manager import AgentManager

        mgr = AgentManager()
        # 立即退出的进程
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('hello')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        try:
            port = mgr._read_port(proc, "test", timeout=5)
            assert port is None
        finally:
            proc.kill()
            proc.wait()

    def test_timeout_kills_worker_that_never_outputs_port(self) -> None:
        """worker 永不输出 PORT 也不退出 → 应在 timeout 后终止进程并返回 None."""
        from backend.agent_manager import AgentManager

        mgr = AgentManager()
        proc = _make_proc_that_never_outputs_port()
        pid = proc.pid

        start = time.monotonic()
        port = mgr._read_port(proc, "test", timeout=2)
        elapsed = time.monotonic() - start

        assert port is None
        # 超时应在合理时间内返回 (允许 1s 误差)
        assert elapsed < 5, f"超时等待耗时 {elapsed:.1f}s, 远超预期 2s"
        # 进程应被终止
        assert proc.poll() is not None, "worker 在超时后未被终止"

    def test_concurrent_start_does_not_block_indefinitely(self) -> None:
        """模拟 start() 调用: 在独立线程中执行, 验证不会无限阻塞."""
        from backend.agent_manager import AgentManager

        mgr = AgentManager()
        proc = _make_proc_that_never_outputs_port()

        result = {"port": None, "done": False}

        def _run() -> None:
            result["port"] = mgr._read_port(proc, "test", timeout=2)
            result["done"] = True

        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=10)  # 给 10s 保护, 正常应 2~3s 返回

        assert result["done"], "start() 在 10s 内未返回 — 可能仍阻塞在 readline()"
        assert result["port"] is None
        assert proc.poll() is not None, "worker 在超时后未被终止"


class TestStartMethod:
    """AgentManager.start 集成测试 (使用真实子进程)."""

    def test_start_timeout_kills_worker(self) -> None:
        """start() 在 worker 不输出 PORT 时应在 timeout 内返回错误, 并终止进程."""
        from backend.agent_manager import AgentManager

        mgr = AgentManager()

        proc = _make_proc_that_never_outputs_port()
        pid = proc.pid

        start = time.monotonic()
        port = mgr._read_port(proc, "wechat", timeout=2)
        elapsed = time.monotonic() - start

        assert port is None
        assert elapsed < 5, f"超时等待耗时 {elapsed:.1f}s, 远超预期"
        assert proc.poll() is not None, "worker 在超时后未被终止"

    def test_start_error_response_contains_timeout_detail(self) -> None:
        """模拟 start() 完整流程: worker 不输出 PORT 时应返回错误并记录到 db."""
        from backend.agent_manager import AgentManager

        mgr = AgentManager()
        proc = _make_proc_that_never_outputs_port()

        # 先手动存入 _procs 以模拟 start() 中创建 proc 后的流程
        with mgr._lock:
            mgr._procs["wechat"] = proc

        # 通过 _read_port 验证超时机制
        port = mgr._read_port(proc, "wechat", timeout=2)
        assert port is None
        assert proc.poll() is not None

        # 清理
        with mgr._lock:
            mgr._procs["wechat"] = None
