"""wxshop 扫描阶段: scan → backfill_room_ids → contact → 写达人跟进表.

多账号轮换 (需求2/4):
  - 用「有联系方式」筛选 (--contact) 爬取, 避免浪费 getTalentContact 每日上限.
  - 从当前账号开始; 若该账号未提取到任何有效联系方式 (大概率次数耗尽, 因筛选
    保证达人有联系方式) → 切换到下一个登录有效的账号重跑.
  - 全部账号都提取不到 → 返回 error: 提醒用户添加新小店账号登录状态,
    或告知 24 点后次数恢复再开始.
  - 成功账号写回 current_account (下次循环默认用它, 不从没次数的开始).

写跟进表 (需求6/7): scan 拿到有联系方式的结果后, 把达人画像 + 微信号/手机号
upsert 进 wxshop-cli/达人跟进表.db (按昵称, 只写爬取列+联系方式, 不覆盖手工列).
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import get_logger
from ..agents import client
from ..paths import CONTACTS_FILE, TALENTS_FILE
from ..services import accounts, followup
from ..state import RecruitState

log = get_logger("scan")


def _run_scan_with(acc: str, cfg) -> bool:
    """用指定账号跑 scan → backfill → contact 三步, 全成功返回 True.

    若 daren-scan 爬取到 0 行 (该账号广场无数据/权限异常), 视为失败,
    避免用空结果覆盖已有 talents.jsonl.
    """
    if not client.call("shop", "scan", cat=cfg.cat or None,
                       max_pages=cfg.max_pages, out=str(TALENTS_FILE),
                       account=acc)["success"]:
        return False
    if _count_rows(TALENTS_FILE) == 0:
        log.warning("账号 %s: daren-scan 爬取到 0 行, 视为失败", acc)
        return False
    if not client.call("shop", "backfill_room_ids", path=str(TALENTS_FILE))["success"]:
        log.warning("账号 %s: 无可用 roomId", acc)
        return False
    if not client.call("shop", "contact", in_path=str(TALENTS_FILE),
                       out_path=str(CONTACTS_FILE), account=acc)["success"]:
        return False
    return True


def _count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


def _has_contacts(path: Path) -> bool:
    """contacts 里是否提取到有效联系方式 (微信号或手机号)."""
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if (r.get("wxId") or r.get("微信号") or r.get("wx_id")
                or r.get("手机号") or r.get("phone")):
            return True
    return False


def _write_followup() -> int:
    """把 talents(画像) + contacts(联系方式) + metrics(带货者信息) 合并 upsert 进达人跟进表.

    metrics 只映射进跟进表列, 不保留在 contacts.jsonl (写库后剥除). 返回写入数.
    """
    if not TALENTS_FILE.exists():
        return 0
    talents: list[dict] = []
    for line in TALENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                talents.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    # nickname → {微信号, 手机号, metrics}
    contacts: dict[str, dict] = {}
    if CONTACTS_FILE.exists():
        for line in CONTACTS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            nick = (r.get("nickname") or "").strip()
            if nick:
                contacts[nick] = {
                    "微信号": (r.get("wxId") or r.get("微信号") or r.get("wx_id") or "").strip(),
                    "手机号": (r.get("手机号") or r.get("phone") or "").strip(),
                    "metrics": r.get("metrics") or None,
                }
    n = 0
    for row in talents:
        nick = (row.get("nickname") or "").strip()
        if followup.upsert_daren(row, contacts.get(nick)):
            n += 1
    _strip_metrics_from_contacts()
    log.info("达人跟进表 upsert: %d/%d 条", n, len(talents))
    return n


def _strip_metrics_from_contacts() -> None:
    """把 CONTACTS_FILE 每行的 metrics key 剥掉重写 (metrics 只进跟进表, 不留在 jsonl)."""
    if not CONTACTS_FILE.exists():
        return
    lines: list[str] = []
    changed = False
    for line in CONTACTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            lines.append(line)
            continue
        if "metrics" in r:
            r.pop("metrics")
            changed = True
        lines.append(json.dumps(r, ensure_ascii=False))
    if changed:
        CONTACTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def scan(state: RecruitState) -> dict:
    cfg = state["config"]
    log.info("── 阶段一: wxshop 扫描达人 + 提取联系方式 (多账号轮换) ──")

    account = accounts.current()
    ordered = [account] + [a for a in accounts.list_accounts() if a != account]
    failures: list[str] = []
    for acc in ordered:
        if not _run_scan_with(acc, cfg):
            failures.append(f"{acc}: scan/提取命令失败")
            log.warning("账号 %s 扫描失败, 尝试下一个", acc)
            continue
        # 需求6: 进入详情页后无论是否提取到联系方式, 达人画像都进跟进表
        # (联系方式列有则填, 没有则留空)
        n = _write_followup()
        if _has_contacts(CONTACTS_FILE):
            accounts.set_current(acc)
            log.info("✅ 账号 %s 成功提取联系方式, 跟进表写入 %d 条", acc, n)
            return {"error": None, "account": acc}
        # 勾选了「有联系方式」筛选仍无任何联系方式 → 可能是提取次数耗尽, 也可能是提取失败
        failures.append(f"{acc}: 未提取到任何联系方式 (可能每日次数耗尽, 也可能提取失败)")
        log.warning("账号 %s 未提取到联系方式, 尝试下一个账号", acc)

    return {"error": (
        "所有小店账号均无法提取联系方式:\n  " + "\n  ".join(failures) + "\n"
        "请添加新的小店账号登录状态 (`wxshop login --account <名称>` 扫码), "
        "或等 24 点后联系方式次数恢复再开始工作流"
    )}