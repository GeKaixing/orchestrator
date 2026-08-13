"""recruit — 达人招商全流程编排器 (LangGraph 版)."""

from __future__ import annotations

import logging

__version__ = "0.1.0"


def get_logger(name: str = "recruit") -> logging.Logger:
    """返回带统一前缀的 logger (由 cli 决定是否 basicConfig)."""
    return logging.getLogger(f"recruit.{name}")
