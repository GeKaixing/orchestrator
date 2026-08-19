"""自动检查更新 — 从 GitHub 仓库的 tag 查询最新版本.

项目以源码包 + setup.bat 分发, 无安装器无法自我替换, 因此这里只负责
「查询远端最新版本并比较」, 由前端提示用户跳转 GitHub 页面手动下载.

实现说明:
- 主路径用 `git ls-remote --tags` 直接读取 git tag (走 git 协议, 不走
  api.github.com, 因此**不需要令牌、不会触发 403 限流**), 即使仓库没发过
  GitHub Release 也能拿到版本号.
- 仅在 git 不可用 / 网络异常时, 才回退到 Release API (可选地配 GITHUB_TOKEN 提额).
"""

from __future__ import annotations

import os
import subprocess
import time

import requests

from . import __version__

REPO = "GeKaixing/orchestrator"
REPO_URL = f"https://github.com/{REPO}.git"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_URL = f"https://github.com/{REPO}/releases/latest"
CACHE_TTL = 600  # 10 分钟, 避免频繁请求

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


def _latest_tag_from_lsremote(stdout: str) -> str:
    """从 `git ls-remote --tags` 的输出里挑出最新 (按语义化版本) 的 tag.

    输出形如:  `<sha>\trefs/tags/v1.2.3` 以及注解 tag 的 `<sha>\trefs/tags/v1.2.3^{}`.
    返回 '' 表示没有任何 tag.
    """
    seen: dict[str, None] = {}
    for line in stdout.splitlines():
        if "\trefs/tags/" not in line:
            continue
        name = line.split("refs/tags/", 1)[1].strip()
        if name.endswith("^{}"):  # 注解 tag 的 deref 行, 去掉后缀
            name = name[:-3]
        seen.setdefault(name, None)
    if not seen:
        return ""
    # 按语义化版本降序排序, 取最高版本; 无法解析的排最后
    tags = sorted(seen, key=lambda t: _parse_version(t), reverse=True)
    return tags[0]


def _github_token() -> str:
    """可选的 GitHub 令牌: 环境变量 GITHUB_TOKEN / GH_TOKEN, 仅用于兜底 API。"""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def check_update(force: bool = False) -> dict:
    """查询 GitHub 最新 tag 并与当前版本比较, 返回结果 dict.

    主路径用 git ls-remote 读取 tag (无需令牌); git 失败才回退到 Release API。
    任何异常都只写进 error 字段, 不影响主流程.
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

    # 主路径: git ls-remote --tags (不经过 API, 无需令牌)
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", REPO_URL],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8,
        )
        if proc.returncode == 0:
            tag = _latest_tag_from_lsremote(proc.stdout)
            if tag:
                result["latest_version"] = tag.lstrip("v")
                result["release_url"] = f"https://github.com/{REPO}/releases/tag/{tag}"
                result["has_update"] = _parse_version(tag) > _parse_version(__version__)
            else:
                result["error"] = "仓库暂无 tag"
        else:
            result["error"] = f"git ls-remote 失败: {proc.stderr.strip() or 'unknown'}"
    except (subprocess.SubprocessError, OSError) as e:
        result.setdefault("error", f"git 调用异常: {e}")

    # 兜底: 仅在 git 路径彻底失败时, 尝试 Release API (可选地配令牌提升配额)
    if not result["latest_version"] and not result.get("error", "").startswith("仓库暂无"):
        token = _github_token()
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "recruit-orchestrator"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = requests.get(API_URL, timeout=8, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                tag = str(data.get("tag_name", "")).strip()
                if tag:
                    result["latest_version"] = tag.lstrip("v")
                    result["notes"] = str(data.get("body", "")).strip()
                    result["has_update"] = _parse_version(tag) > _parse_version(__version__)
                    result["error"] = ""
                else:
                    result["error"] = "仓库暂无 release"
            elif resp.status_code != 404:
                result.setdefault("error", f"GitHub API 返回 HTTP {resp.status_code}")
        except requests.RequestException as e:
            result.setdefault("error", f"网络异常: {e}")

    _CACHE["ts"] = now
    _CACHE["result"] = result
    return result
