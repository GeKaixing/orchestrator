"""前置自检节点 — 并行探测 agent 健康 + 多账号选择 (需求 1/2/3).

需求1: 判断微信小店是否登录, 未登录提醒用户登录.
需求2: 多账号轮换 — 从当前账号开始, 未登录则换下一个; 全未登录 → 提醒用户
       添加新账号登录状态, 并告知 24 点后联系方式次数恢复再开始.
需求3: 判断微信是否正确打开并登录 (进程 + 主窗口标题), 未打开提醒打开/登录.

账号选择结果写回 current_account (settings), 供 scan/invite 等后续节点沿用.
"""

from __future__ import annotations

from .. import get_logger
from ..agents import client
from ..services import accounts
from ..state import RecruitState

log = get_logger("preflight")

# 需要小店账号的阶段 (shop 登录/次数/账号选择)
_SHOP_STAGES = ("all", "scan", "im", "invite", "reply")
# 需要微信桌面端的阶段
_WECHAT_STAGES = ("all", "add", "send", "invite")


def preflight(state: RecruitState) -> dict:
    cfg = state["config"]
    healths = client.health_all()
    shop_ok = healths.get("shop", {}).get("ok", False)
    wechat_ok = healths.get("wechat", {}).get("ok", False)
    rag_ok = healths.get("rag", {}).get("ok", False)

    # ── 需求 1/2: 小店登录 + 多账号选择 ──
    if cfg.stage in _SHOP_STAGES:
        acc, err = accounts.next_available()
        if not acc:
            # err 已含: 所有账号未登录 → 提醒添加新账号 / 24 点后次数恢复
            return {"error": err}
        shop_ok = True  # next_available 已逐账号 verify 登录有效
        log.info("本轮小店账号: %s (%s)", acc,
                 accounts.account_nickname(acc) or acc)
    elif not shop_ok and cfg.stage == "send":
        # 纯 send 阶段也走小店? 不, send 是微信发消息; 无需 shop
        pass

    # ── 需求 3: 微信打开并登录 ──
    if cfg.stage in _WECHAT_STAGES and not wechat_ok:
        detail = healths.get("wechat", {}).get("detail", "")
        return {"error": f"微信未打开或未登录: {detail}。请先打开微信桌面端并扫码登录"}

    if cfg.stage in ("all", "send") and cfg.watch:
        client.call("wechat", "check_rag")
    if cfg.stage == "reply" and not rag_ok:
        detail = healths.get("rag", {}).get("detail", "")
        return {"error": f"rag 服务不可用 (localhost:2024), 无法自动回复 ({detail})"}

    log.info("前置自检通过: shop=%s wechat=%s rag=%s", shop_ok, wechat_ok, rag_ok)
    return {"error": None}