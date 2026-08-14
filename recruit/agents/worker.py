"""Agent Worker — 常驻进程, 通过 localhost TCP JSON 行协议对外服务.

用法:
  python -m recruit.agents.worker <name> [--port N]   # N=0 随机端口
  python -m recruit.agents.worker <name> --selftest    # 跑一次 health 即退出

请求/响应 (newline-delimited JSON):
  请求  {"id": 1, "method": "health"} | {"id": 1, "method": "call", "action": "...", "params": {...}}
  响应  {"id": 1, "ok": true, "result": {...}} | {"id": 1, "ok": false, "error": "..."}

health 请求即时响应 (线程池, 不排队), call 请求串行执行 (锁):
  天然序列化微信 UI 自动化动作, 同时避免长任务 (如 hermes chat 几十秒) 堵死健康检查.
stdout 只输出一行 "PORT <n>" 供 Manager 捕获; 日志走 stderr.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from .. import get_logger
from . import registry

log = get_logger("worker")

_call_lock = threading.Lock()  # call 串行锁: health 不抢锁即时响应


def _handle(agent, method: str, payload: dict) -> dict:
    if method == "health":
        return agent.health_check()
    if method == "call":
        return agent.run(payload.get("action") or "", **(payload.get("params") or {}))
    return {"ok": False, "detail": f"未知 method: {method}"}


def _process_one(agent, conn: socket.socket) -> None:
    try:
        f = conn.makefile("r", encoding="utf-8", errors="replace")
        line = f.readline()
        if not line:
            return
        req = json.loads(line)
        req_id = req.get("id")
        method = req.get("method") or "health"
        if method == "call":
            with _call_lock:
                result = _handle(agent, method, req)
        else:
            result = _handle(agent, method, req)
        resp = {"id": req_id, "ok": True, "result": result}
    except Exception as e:  # noqa: BLE001
        log.error("处理请求异常: %s", e)
        resp = {"id": req_id, "ok": False, "error": str(e)}
    try:
        conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception:  # noqa: BLE001
        pass


def serve(agent, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen(64)
        actual = sock.getsockname()[1]
        print(f"PORT {actual}", flush=True)
        log.info("worker %s 就绪, 监听 127.0.0.1:%d", agent.name, actual)
        with ThreadPoolExecutor(max_workers=16, thread_name_prefix=f"wkr-{agent.name}") as ex:
            while True:
                conn, _ = sock.accept()
                ex.submit(_process_one, agent, conn)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Agent worker")
    p.add_argument("name", help="agent 名: wechat|shop|rag|hermes")
    p.add_argument("--port", type=int, default=0, help="监听端口 (0=随机)")
    p.add_argument("--selftest", action="store_true", help="跑一次 health 后退出")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S", stream=sys.stderr,
    )

    try:
        agent = registry.get(args.name)
    except KeyError as e:
        log.error("%s", e)
        return 1

    if args.selftest:
        print(json.dumps(agent.health_check(), ensure_ascii=False), flush=True)
        return 0

    serve(agent, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
