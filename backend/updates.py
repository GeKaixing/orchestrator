"""自动检查更新 — 从 GitHub Releases 查询最新版本.

项目以源码包 + setup.bat 分发, 无安装器无法自我替换, 因此这里只负责
「查询远端最新版本并比较」, 由前端提示用户跳转 GitHub release 页手动下载.
"""

from __future__ import annotations

import time

import requests

from . import __version__

REPO = "GeKaixing/orchestrator"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_URL = f"https://github.com/{REPO}/releases/latest"
CACHE_TTL = 600  # 10 分钟, 避免打爆 GitHub 未认证限流 (60 次/时)

_CACHE: dict = {"ts": 0.0, "result": None}


def _parse_version(s: str) -> tuple[int, ...]:
    """把 'v0.0.2' / '0.0.2' 解析成可比较的 int 元组, 非数字段兜底为 0."""
    parts = s.strip().lstrip("v").replace("_", ".").split(".")
    nums: list[int] = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    return tuple(nums)


def check_update(force: bool = False) -> dict:
    """查询 GitHub 最新 release 并与当前版本比较, 返回结果 dict.

    结果缓存 CACHE_TTL 秒; 网络异常/无 release/非 200 都不抛异常,
    只把原因放进 error 字段, 保证不影响主流程.
    """
    now = time.time()
    if (
        not force
        and _CACHE["result"] is not None
        and now - _CACHE["ts"] < CACHE_TTL
    ):
        return _CACHE["result"]

    result: dict = {
        "current_version": __version__,
        "latest_version": "",
        "has_update": False,
        "release_url": RELEASE_URL,
        "notes": "",
        "error": "",
        "checked_at": now,
    }
    try:
        resp = requests.get(
            API_URL,
            timeout=8,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "recruit-orchestrator",
            },
        )
        if resp.status_code == 404:
            result["error"] = "仓库暂无 release"
        elif resp.status_code != 200:
            result["error"] = f"GitHub API 返回 HTTP {resp.status_code}"
        else:
            data = resp.json()
            latest = str(data.get("tag_name", "")).strip()
            result["latest_version"] = latest.lstrip("v")
            result["notes"] = str(data.get("body", "")).strip()
            if latest:
                result["has_update"] = _parse_version(latest) > _parse_version(__version__)
    except requests.RequestException as e:
        result["error"] = f"网络异常: {e}"
    except ValueError as e:
        result["error"] = f"响应解析失败: {e}"

    _CACHE["ts"] = now
    _CACHE["result"] = result
    return result
