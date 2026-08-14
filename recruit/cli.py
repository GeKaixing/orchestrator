"""CLI 入口 — 解析参数 → 构造 config → 编排 LangGraph."""

from __future__ import annotations

import argparse
import logging
import sys

from . import get_logger, paths
from .config import RecruitConfig, resolve_text
from .graph import build_graph
from .services import db

log = get_logger("cli")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="达人招商全流程编排 (LangGraph)")
    p.add_argument("--contacts", default="", help="直接用现成 contacts.jsonl, 跳过 wxshop 阶段")
    p.add_argument("--cat", default="", help="daren-scan 达人类目筛选 (缺省爬全量有联系方式)")
    p.add_argument("--max-pages", type=int, default=1, help="daren-scan 页数 (首轮 1 页)")
    p.add_argument("--limit", type=int, default=10, help="本轮最多处理 N 个 wxid")
    p.add_argument("--text", default="", help="招商文案 (缺省读 .env 的 RECRUIT_TEXT)")
    p.add_argument("--stage", default="all",
                   choices=["scan", "add", "send", "im", "reply", "invite", "all"],
                   help="只跑指定阶段 (im=小店官方IM招商, reply=IM自动回复, invite=IM 5条邀约→微信复邀)")
    p.add_argument("--watch", action="store_true",
                   help="发完后持续自动回复 (请单独跑 send_message.py --watch 更可控)")
    p.add_argument("--retry", type=int, default=1,
                   help="每个动作失败后额外重试次数 (缺省 1)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.watch:
        log.warning("--watch 不在编排内实现; 想盯某个达人的持续回复请单独运行:")
        log.warning("  uv run python scripts/send_message.py --wxid <微信号> --watch")

    text = resolve_text(args.text)
    cfg = RecruitConfig(
        stage=args.stage,
        contacts=args.contacts,
        cat=args.cat,
        max_pages=args.max_pages,
        limit=args.limit,
        text=text,
        watch=args.watch,
        retry=args.retry,
    )
    if cfg.needs_text() and not text:
        log.error("需要招商文案: 传 --text 或在 .env 设置 RECRUIT_TEXT")
        return 1

    paths.WORK_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()

    graph = build_graph()
    result = graph.invoke(
        {"config": cfg, "text": text, "contacts": [], "todo": [], "rooms": [],
         "results": {}, "error": None, "no_contacts": None, "scan_saved": None},
        config={"recursion_limit": 200},
    )
    if result.get("error"):
        log.error("编排失败: %s", result["error"])
        return 1
    log.info("🏁 编排结束, 报告: %s", paths.REPORT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
