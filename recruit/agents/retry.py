"""重试包装 — 对返回 AgentResult 的动作: success=False 时按退避重试."""

from __future__ import annotations

import time
from collections.abc import Callable

from .. import get_logger
from .base import AgentResult

log = get_logger("agents.retry")


def retry_result(
    fn: Callable[[], AgentResult],
    attempts: int = 2,
    backoff: float = 3.0,
    label: str = "",
) -> AgentResult:
    """调用 fn 直到成功或达到 attempts 次; 每次失败后 sleep backoff 秒."""
    for i in range(attempts):
        res = fn()
        if res["success"]:
            return res
        if i < attempts - 1:
            log.warning("[%s] 第 %d/%d 次失败: %s, %ss 后重试",
                        label, i + 1, attempts, res.get("error"), backoff)
            time.sleep(backoff)
    return res
