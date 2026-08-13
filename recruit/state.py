"""LangGraph State 定义."""

from __future__ import annotations

from typing import Annotated, TypedDict

from .config import RecruitConfig


def merge_results(cur: dict | None, upd: dict) -> dict:
    """results 通道的累加 reducer: 各 Send 分支的 wxid 结果逐条并入."""
    return {**(cur or {}), **upd}


class RecruitState(TypedDict):
    """主图状态."""

    config: RecruitConfig
    text: str
    contacts: list[dict]                       # 全部有效联系人
    todo: list[dict]                           # 本轮待处理
    rooms: list[dict]                          # im 模式
    results: Annotated[dict, merge_results]    # wxid -> {stage, reason, updated}
    error: str | None


class ContactState(TypedDict):
    """每联系人子图状态 (Send 分支)."""

    contact: dict
    text: str
    actions: list[str]                         # ["add"] / ["send"] / ["add","send"]
    result: dict | None
    results: Annotated[dict, merge_results]
