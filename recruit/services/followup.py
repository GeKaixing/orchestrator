"""达人跟进表.db 读写 — orchestrator 侧 (与 wxshop-cli `daren-scan --db` 共用同一张表).

跟进表 = 「达人跟进表」Excel 转 SQLite, 主表 48 列 (DDL 与 wxshop cli.py _DB_DDL 一致).
铁律: 只写「爬取列 + 联系方式 + 跟进状态/备注」, 手工列 (有无竞品/备注/寄样品等) 一律不覆盖.
按达人昵称 upsert: 已存在 → 更新爬取列/联系方式; 不存在 → 插入新行 (登记时间=今天).
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from typing import Any

from .. import get_logger
from .. import paths

log = get_logger("followup")

# 表结构 (与 wxshop-cli/wxshop/cli.py 的 _DB_DDL 保持一致)
_DB_DDL = """CREATE TABLE IF NOT EXISTS "达人跟进表" (
  "达人昵称" TEXT, "达人昵称-是否重复" TEXT, "跟进状态" TEXT, "微信号" TEXT, "手机号" TEXT,
  "有无竞品" TEXT, "优势备注" TEXT, "劣势备注" TEXT, "不合作寄样品" TEXT, "备注不合作问题" TEXT,
  "合作寄样品" TEXT, "备注合作效果" TEXT, "备注原因" TEXT, "达人评分" REAL, "带货销售额" TEXT,
  "客单价" TEXT, "粉丝数" TEXT, "合作方式" TEXT, "粉丝特征-性别" TEXT, "粉丝特征-年龄" TEXT,
  "粉丝特征-地域" TEXT, "粉丝特征-人群" TEXT, "粉丝特征-购物偏好" TEXT, "粉丝特征-购买力" TEXT,
  "粉丝特征(汇总)" TEXT, "总销量" TEXT, "跟买人数" TEXT, "回头客" INTEGER, "品类占比1" TEXT,
  "品类占比2" TEXT, "品类占比3" TEXT, "来源页面" TEXT, "采集时间" TEXT,
  "直播带货-直播销售额" TEXT, "直播带货-场均成交额" TEXT, "直播带货-场均观看人数" TEXT,
  "直播带货-总带货场次" INTEGER, "短视频带货-视频销售额" TEXT, "短视频带货-条均成交额" TEXT,
  "短视频带货-条均点赞数" INTEGER, "短视频带货-总带货条数" INTEGER, "登记时间" TEXT,
  "带货销售额格式化" TEXT, "达人场均成交额格式化" INTEGER, "达人销售额等级" TEXT,
  "达人场均成交额等级" TEXT, "达人评分等级" TEXT, "达人等级" TEXT
)"""


def _connect() -> sqlite3.Connection:
    paths.FOLLOWUP_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(paths.FOLLOWUP_DB), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(_DB_DDL)
    conn.commit()
    return conn


def _today() -> str:
    now = datetime.now()
    return f"{now.year}年{now.month}月{now.day}日"


def _to_score(v: Any) -> float | None:
    """评分文本 → float (如 '4.68'→4.68, 空/未知→None)."""
    import re

    s = str(v or "").strip()
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _fmt_wan(v: Any) -> str:
    """带货销售额格式化: 字符串透传 (整数不带 .0)."""
    if v in (None, ""):
        return ""
    return str(v)


# ── 昵称定位 (同昵称重复只更新第一条, 与 wxshop _db_upsert 一致) ─────────
def _find_rowid(conn: sqlite3.Connection, nick: str) -> int | None:
    row = conn.execute(
        'SELECT rowid FROM "达人跟进表" WHERE "达人昵称" = ? ORDER BY rowid LIMIT 1',
        (nick,),
    ).fetchone()
    return row["rowid"] if row else None


def _upsert_row(conn: sqlite3.Connection, nick: str, values: dict[str, Any]) -> None:
    rid = _find_rowid(conn, nick)
    if rid is not None:
        set_clause = ", ".join(f'"{k}" = ?' for k in values)
        conn.execute(f'UPDATE "达人跟进表" SET {set_clause} WHERE rowid = ?',
                     [*values.values(), rid])
        return
    cols = ["达人昵称", *values.keys(), "登记时间"]
    col_sql = ", ".join('"%s"' % c for c in cols)
    qs = ", ".join("?" for _ in cols)
    conn.execute(f'INSERT INTO "达人跟进表" ({col_sql}) VALUES ({qs})',
                 [nick, *values.values(), _today()])


# ── 公开 API ─────────────────────────────────────────────────────────
def upsert_daren(row: dict, contacts: dict | None = None) -> dict | None:
    """把一条达人记录 upsert 进跟进表 (爬取列 + 联系方式).

    row 来自 talents/contacts.jsonl; contacts: {微信号, 手机号} (可空).
    返回新/更新后的行 dict, 失败返回 None.
    """
    nick = (row.get("nickname") or "").strip()
    if not nick:
        return None
    gmv = row.get("gmv") or ""
    values: dict[str, Any] = {
        "达人评分": _to_score(row.get("score")),
        "带货销售额": gmv,
        "带货销售额格式化": _fmt_wan(gmv),
        "粉丝数": row.get("fans") or "",
        "直播带货-直播销售额": row.get("liveGmv") or "",
        "短视频带货-视频销售额": row.get("videoGmv") or "",
        "来源页面": row.get("url") or row.get("达人详细链接") or "",
        "采集时间": _today(),
        "达人销售额等级": row.get("达人销售额等级") or "",
        "达人评分等级": row.get("达人评分等级") or "",
    }
    c = contacts or {}
    if c.get("微信号"):
        values["微信号"] = c["微信号"]
    if c.get("手机号"):
        values["手机号"] = c["手机号"]
    # 顺带记录 room_id 供 orchestrator 索引 (跟进表没有该列, 用备注原因不覆盖 →
    # 这里不写 room_id; roomId 仍由 contacts.jsonl / darens 表维护)
    try:
        conn = _connect()
        try:
            _upsert_row(conn, nick, values)
            conn.commit()
            return get_daren(nick)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.error("跟进表 upsert 失败 (%s): %s", nick, e)
        return None


def mark_status(nickname: str, status: str, reason: str = "") -> None:
    """标记达人跟进状态 (需求9: 加好友失败/已加好友/无联系方式等) + 备注原因.

    只写「跟进状态」「备注原因」两列, 其余手工列不动.
    """
    nick = (nickname or "").strip()
    if not nick:
        return
    values: dict[str, Any] = {}
    if status:
        values["跟进状态"] = status
    if reason:
        values["备注原因"] = reason
    if not values:
        return
    try:
        conn = _connect()
        try:
            rid = _find_rowid(conn, nick)
            if rid is None:
                _upsert_row(conn, nick, values)
            else:
                set_clause = ", ".join(f'"{k}" = ?' for k in values)
                conn.execute(f'UPDATE "达人跟进表" SET {set_clause} WHERE rowid = ?',
                             [*values.values(), rid])
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.error("跟进表 mark_status 失败 (%s): %s", nick, e)


def get_daren(nickname: str) -> dict | None:
    nick = (nickname or "").strip()
    if not nick:
        return None
    try:
        conn = _connect()
        try:
            row = conn.execute(
                'SELECT * FROM "达人跟进表" WHERE "达人昵称" = ? ORDER BY rowid LIMIT 1',
                (nick,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.error("跟进表查询失败 (%s): %s", nick, e)
        return None


def list_darens() -> list[dict]:
    try:
        conn = _connect()
        try:
            rows = conn.execute('SELECT * FROM "达人跟进表" ORDER BY rowid').fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.error("跟进表列表失败: %s", e)
        return []
