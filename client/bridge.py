"""线程 → 主线程 的消息桥.

worker 的后台线程只往 Queue 里 push, 主线程每 100ms drain 一次队列,
把消息分发给注册的 handler, 避免跨线程直接操作 Tk 控件.
"""

from __future__ import annotations

import queue
from typing import Any, Callable


class QueueBridge:
    """单桥多 handler: push(type, payload) → 各 type 的 handler 逐个收到 payload."""

    def __init__(self, root) -> None:
        self._root = root
        self._q: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._handlers: dict[str, list[Callable[[Any], None]]] = {}
        self._after_id: str | None = None

    def register(self, msg_type: str, fn: Callable[[Any], None]) -> None:
        self._handlers.setdefault(msg_type, []).append(fn)

    def push(self, msg_type: str, payload: Any = None) -> None:
        self._q.put((msg_type, payload))

    def start(self) -> None:
        def _drain() -> None:
            while True:
                try:
                    msg_type, payload = self._q.get_nowait()
                except queue.Empty:
                    break
                for fn in self._handlers.get(msg_type, []):
                    try:
                        fn(payload)
                    except Exception:  # noqa: BLE001  UI handler 出错不能拖垮 drain
                        pass
            self._after_id = self._root.after(100, _drain)

        _drain()

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None
