#!/usr/bin/env python3
"""
recruit_orchestrator.py — 达人招商全流程编排

串联三个项目:
  1. wxshop-cli      : daren-scan(有联系方式) -> daren-contact(提取 wxId/phoneNumber)
  2. wechat-friend-add: add_friend.py 加好友 -> send_message.py 发招商文案
  3. rag             : send_message.py 的自动回复走 rag 服务 (发送固定文案不依赖 rag)

用法 (在 wechat-friend-add 项目根目录运行):
  uv run python scripts/recruit_orchestrator.py --limit 10                # 全流程
  uv run python scripts/recruit_orchestrator.py --contacts FILE --limit 10  # 跳过 wxshop, 直接用现成 contacts
  uv run python scripts/recruit_orchestrator.py --stage add --limit 10    # 只跑加好友

前置条件:
  - wxshop 登录态有效 (cd wxshop-cli && .venv/Scripts/python -m wxshop login 扫码)
  - 微信桌面端已打开并登录
  - 招商文案: --text 或 .env 的 RECRUIT_TEXT

工作区: ~/Desktop/orchestrator/ (talents.jsonl / contacts.jsonl / recruit_state.json / recruit_report.md)
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# 依赖 wechat-friend-add 的 wechat_core / rag_client, 把其 scripts 目录加进 path
sys.path.insert(0, os.path.join(os.path.expanduser("~/Desktop"), "wechat-friend-add", "scripts"))

from wechat_core import PROJECT_DIR, setup_logger

log = setup_logger("recruit_orchestrator")

# ── 路径 ─────────────────────────────────────────────────────
WORK_DIR = Path(os.path.expanduser("~/Desktop/orchestrator"))
WXSHOP_DIR = Path(os.path.expanduser("~/Desktop/wxshop-cli"))
STATE_FILE = WORK_DIR / "recruit_state.json"
REPORT_FILE = WORK_DIR / "recruit_report.md"

STAGES_DONE = {"sent", "im_sent"}


def _venv_python(project_dir: Path) -> str | None:
    """Windows: .venv/Scripts/python.exe; Unix: .venv/bin/python"""
    for p in (
        project_dir / ".venv" / "Scripts" / "python.exe",
        project_dir / ".venv" / "bin" / "python",
    ):
        if p.exists():
            return str(p)
    return None


def _run(cmd: list[str], cwd: Path, timeout: int = 600, label: str = "") -> subprocess.CompletedProcess | None:
    log.info("RUN [%s] %s (cwd=%s)", label, " ".join(cmd), cwd)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        log.error("[%s] 执行超时 (%ds)", label, timeout)
        return None
    except Exception as e:
        log.error("[%s] 执行异常: %s", label, e)
        return None
    for line in (proc.stdout or "").splitlines():
        log.info("  [%s out] %s", label, line)
    for line in (proc.stderr or "").splitlines():
        log.info("  [%s err] %s", label, line)
    log.info("[%s] 退出码 %s", label, proc.returncode)
    return proc


# ── 前置自检 ─────────────────────────────────────────────────
def check_wechat() -> bool:
    from wechat_core import get_wechat_pid
    pid = get_wechat_pid()
    if pid:
        log.info("✅ 微信桌面端运行中 pid=%s", pid)
        return True
    log.error("❌ 微信桌面端未运行，请先打开并登录微信")
    return False


def check_wxshop_login() -> bool:
    py = _venv_python(WXSHOP_DIR)
    if not py:
        log.error("❌ 找不到 wxshop-cli 的 venv: %s", WXSHOP_DIR)
        return False
    proc = _run([py, "-m", "wxshop", "persist", "verify"], WXSHOP_DIR, timeout=120, label="wxshop-persist")
    if proc is None or proc.returncode != 0:
        log.error("❌ wxshop 登录态失效，请先扫码: cd wxshop-cli && .venv/Scripts/python -m wxshop login")
        return False
    log.info("✅ wxshop 登录态有效")
    return True


def check_rag() -> bool:
    try:
        import rag_client
        if rag_client.available():
            log.info("✅ rag 服务可用")
            return True
    except Exception as e:
        log.error("rag 自检异常: %s", e)
    log.error("❌ rag 服务不可用 (localhost:2024)，自动回复需要它；仅发固定文案可忽略")
    return False


# ── 招商文案 ─────────────────────────────────────────────────
def _load_env() -> dict:
    env: dict[str, str] = {}
    path = PROJECT_DIR / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolve_text(args_text: str | None) -> str:
    if args_text:
        return args_text.strip()
    text = _load_env().get("RECRUIT_TEXT", "").strip()
    if text:
        return text
    return ""


# ── 状态管理 ─────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("读取 %s 失败: %s", STATE_FILE, e)
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── wxshop 阶段 ──────────────────────────────────────────────
def run_scan(talents: Path, cat: str | None = None, max_pages: int = 1) -> bool:
    py = _venv_python(WXSHOP_DIR)
    if not py:
        log.error("找不到 wxshop venv")
        return False
    # --with-im: 逐条建 IM 房间输出 imUrl(含 roomId)。daren-contact 批量按 roomId 提取,
    # 不加 --with-im 则 talents 里没有 roomId, contact 会全部 skipped。
    cmd = [py, "-m", "wxshop", "daren-scan", "--contact", "--with-im",
           "--max-pages", str(max_pages), "--out", str(talents)]
    if cat:
        cmd += ["--cat", cat]
    proc = _run(cmd, WXSHOP_DIR, timeout=1800, label="scan")
    return proc is not None and proc.returncode == 0 and talents.exists()


def backfill_room_ids(talents: Path) -> int:
    """scan --with-im 只输出 imUrl(含 roomId) 字段, 把 roomId 回填到每行,
    供 daren-contact 批量按 roomId 提取联系方式。"""
    rows: list[dict] = []
    for line in talents.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not (r.get("roomId") or r.get("room_id")):
            m = re.search(r"roomId=([^&]+)", r.get("imUrl") or "")
            if m:
                r["roomId"] = m.group(1)
        rows.append(r)
    talents.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                       encoding="utf-8")
    filled = sum(1 for r in rows if r.get("roomId") or r.get("room_id"))
    log.info("回填 roomId: %d/%d 行", filled, len(rows))
    return filled


def run_contact(talents: Path, contacts: Path) -> bool:
    py = _venv_python(WXSHOP_DIR)
    if not py:
        log.error("找不到 wxshop venv")
        return False
    proc = _run([py, "-m", "wxshop", "daren-contact", "--in", str(talents), "--out", str(contacts)],
                WXSHOP_DIR, timeout=1800, label="contact")
    return proc is not None and proc.returncode == 0 and contacts.exists()


def load_contacts(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        log.error("❌ contacts 文件不存在: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    valid: list[dict] = []
    for r in rows:
        # daren-contact 批量写「微信号」, 单条/历史文件写 wxId, 兼容两者
        wxid = (r.get("wxId") or r.get("微信号") or r.get("wx_id") or "").strip()
        if not wxid or wxid.lower() == "(empty)":
            continue
        valid.append({"wxid": wxid, "nickname": (r.get("nickname") or "?").strip()})
    log.info("contacts: %d 行, 有效 wxId %d 个", len(rows), len(valid))
    return valid


def load_rooms(path: Path) -> list[dict]:
    """读 contacts 里有 roomId 的行 (小店官方 IM 房间), 供 im-send 招商."""
    rooms: list[dict] = []
    if not path.exists():
        log.error("❌ contacts 文件不存在: %s", path)
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        rid = (r.get("roomId") or r.get("room_id") or "").strip()
        if rid:
            rooms.append({"roomId": rid, "nickname": (r.get("nickname") or "?").strip(),
                          "wxid": f"im:{rid}"})
    log.info("contacts: %d 行, 可用 roomId %d 个", len(rooms), len(rooms))
    return rooms


# ── 微信动作阶段 ─────────────────────────────────────────────
def run_add_friend(wxid: str) -> tuple[bool, str]:
    py = _venv_python(PROJECT_DIR)
    if not py:
        log.error("找不到 wechat-friend-add 的 venv: %s", PROJECT_DIR)
        return False, "找不到 wechat-friend-add venv"
    proc = _run([py, "scripts/add_friend.py", "--wxid", wxid],
                PROJECT_DIR, timeout=180, label=f"add:{wxid}")
    if proc is not None and proc.returncode == 0:
        return True, ""
    return False, f"add_friend 退出码 {proc.returncode if proc else '异常'}"


def run_send_message(wxid: str, text: str) -> tuple[bool, str]:
    py = _venv_python(PROJECT_DIR)
    if not py:
        log.error("找不到 wechat-friend-add 的 venv: %s", PROJECT_DIR)
        return False, "找不到 wechat-friend-add venv"
    proc = _run([py, "scripts/send_message.py", "--wxid", wxid, "--text", text],
                PROJECT_DIR, timeout=300, label=f"send:{wxid}")
    if proc is not None and proc.returncode == 0:
        return True, ""
    return False, f"send_message 退出码 {proc.returncode if proc else '异常'}"


def run_im_send(room_id: str, text: str) -> tuple[bool, str]:
    """小店官方 IM 招商: wxshop im-chat 在达人 IM 房间发消息 (UI 模式).

    注意: im-send 的 API /shop/kf/cgi/im/send 已失效(404), 只能走 im-chat UI 路径.
    im-chat 打开 IM 页 -> 填 textarea -> Enter, 以 stdout 含 "ok": true 判定页面操作成功.
    """
    py = _venv_python(WXSHOP_DIR)
    if not py:
        return False, "找不到 wxshop venv"
    proc = _run([py, "-m", "wxshop", "im-chat", "--room-id", room_id, "--message", text],
                WXSHOP_DIR, timeout=120, label=f"im:{room_id}")
    if proc is not None and proc.returncode == 0 and '"ok": true' in (proc.stdout or ""):
        return True, ""
    return False, f"im-chat 退出码 {proc.returncode if proc else '异常'}"


def load_my_appid() -> str:
    """读自己店铺 appid (~/.wxshop/api_config.json), 用于识别对方(达人)消息."""
    cfg = Path(os.path.expanduser("~/.wxshop/api_config.json"))
    try:
        return (json.loads(cfg.read_text(encoding="utf-8")) or {}).get("appid", "")
    except Exception:
        return ""


def run_im_messages(room_id: str) -> list[dict] | None:
    """调 wxshop im-messages 读房间消息 (已过滤系统消息)."""
    py = _venv_python(WXSHOP_DIR)
    if not py:
        return None
    proc = _run([py, "-m", "wxshop", "im-messages", "--room-id", room_id],
                WXSHOP_DIR, timeout=90, label=f"immsg:{room_id}")
    if proc is None or proc.returncode != 0:
        return None
    lines = (proc.stdout or "").strip().splitlines()
    if not lines:
        return None
    try:
        data = json.loads(lines[-1])
    except Exception:
        return None
    return data.get("messages") or []


def run_reply(args) -> int:
    """单轮扫描已招商 IM 房间: 达人新消息 -> rag 作答 -> im-chat 回复. 按 msgId 去重."""
    my_appid = load_my_appid()
    if not my_appid:
        log.error("❌ 读不到店铺 appid: ~/.wxshop/api_config.json")
        return 1
    import rag_client
    if not rag_client.available():
        log.error("❌ rag 服务不可用 (localhost:2024), 无法自动回复")
        return 1

    contacts_path = Path(args.contacts) if args.contacts else WORK_DIR / "contacts.jsonl"
    rooms = load_rooms(contacts_path)
    if not rooms:
        log.error("❌ contacts 里没有可用 roomId")
        return 1

    state = load_state()
    total_replied = 0
    for r in rooms:
        room_id, nick = r["roomId"], r["nickname"]
        key = r["wxid"]
        msgs = run_im_messages(room_id)
        if not msgs:
            log.warning("%s: 读消息失败/无消息", nick)
            continue
        st = state.setdefault(key, {"wxid": key, "nickname": nick, "roomId": room_id,
                                    "stage": "im_sent", "replied_msg_ids": [],
                                    "updated": time.strftime("%Y-%m-%d %H:%M:%S")})
        replied = set(st.get("replied_msg_ids") or [])
        new_msgs = [m for m in msgs
                    if m.get("sender") and m["sender"] != my_appid
                    and m.get("msgId") and m["msgId"] not in replied
                    and (m.get("content") or "").strip()]
        if not new_msgs:
            log.info("%s: 无新消息 (%d 条历史)", nick, len(msgs))
            continue
        for m in new_msgs:
            content = m["content"].strip()
            log.info("%s: 达人消息: %s", nick, content[:60])
            result = rag_client.ask(content, thread_id=rag_client.get_thread(room_id))
            if "error" in result:
                log.error("%s: rag 失败: %s", nick, result["error"])
                continue
            rag_client.set_thread(room_id, result["thread_id"])
            reply = rag_client.collapse_reply(result["reply"])
            ok, reason = run_im_send(room_id, reply)
            if ok:
                replied.add(m["msgId"])
                total_replied += 1
                log.info("%s: ✅ rag 回复已发送 (%d 字)", nick, len(reply))
            else:
                log.error("%s: 回复发送失败: %s", nick, reason)
        st["replied_msg_ids"] = sorted(replied)
        st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_state(state)

    log.info("🏁 本轮回复 %d 条新消息", total_replied)
    return 0


# ── 报告 ─────────────────────────────────────────────────────
def write_report(state: dict, todo: list[dict], done_count: int = 0) -> None:
    lines = [
        "# 达人招商编排报告",
        "",
        f"- 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 本轮处理: {len(todo)} 个 (另 {done_count} 个此前已完成, 已跳过)",
        "",
        "| 微信号 | 昵称 | 阶段 | 备注 |",
        "|---|---|---|---|",
    ]
    for it in todo:
        wxid = it["wxid"]
        st = state.get(wxid, {})
        stage = st.get("stage", "pending")
        reason = st.get("reason", "") or ""
        lines.append(f"| {wxid} | {it['nickname']} | {stage} | {reason} |")
    lines.append("")
    counts: dict[str, int] = {}
    for it in todo:
        stage = state.get(it["wxid"], {}).get("stage", "pending")
        counts[stage] = counts.get(stage, 0) + 1
    lines.append("## 汇总")
    lines.append("")
    for k in sorted(counts):
        lines.append(f"- {k}: {counts[k]}")
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    log.info("报告已生成: %s", REPORT_FILE)


def main() -> int:
    parser = argparse.ArgumentParser(description="达人招商全流程编排")
    parser.add_argument("--contacts", default="", help="直接用现成 contacts.jsonl, 跳过 wxshop 阶段")
    parser.add_argument("--cat", default="", help="daren-scan 达人类目筛选 (缺省爬全量有联系方式)")
    parser.add_argument("--max-pages", type=int, default=1, help="daren-scan 页数 (首轮 1 页)")
    parser.add_argument("--limit", type=int, default=10, help="本轮最多处理 N 个 wxid")
    parser.add_argument("--text", default="", help="招商文案 (缺省读 .env 的 RECRUIT_TEXT)")
    parser.add_argument("--stage", default="all", choices=["scan", "add", "send", "im", "reply", "all"], help="只跑指定阶段 (im=小店官方IM招商, reply=IM自动回复)")
    parser.add_argument("--watch", action="store_true", help="发完后持续自动回复 (请单独跑 send_message.py --watch 更可控)")
    args = parser.parse_args()

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    if args.watch:
        log.warning("--watch 不在编排内实现; 想盯某个达人的持续回复请单独运行:")
        log.warning("  uv run python scripts/send_message.py --wxid <微信号> --watch")

    text = resolve_text(args.text)
    if args.stage in ("all", "send") and not text:
        log.error("❌ 需要招商文案: 传 --text 或在 .env 设置 RECRUIT_TEXT")
        return 1

    # 小店官方 IM 招商: 用已有 contacts 里的 roomId 逐个 im-send (无需微信好友)
    if args.stage == "im":
        if not text:
            log.error("❌ 需要招商文案: 传 --text 或在 .env 设置 RECRUIT_TEXT")
            return 1
        if not check_wxshop_login():
            return 1
        contacts_path = Path(args.contacts) if args.contacts else WORK_DIR / "contacts.jsonl"
        rooms = load_rooms(contacts_path)
        if not rooms:
            log.error("❌ contacts 里没有可用 roomId")
            return 1
        state = load_state()
        todo = [r for r in rooms if state.get(r["wxid"], {}).get("stage") not in STAGES_DONE]
        if args.limit and args.limit > 0:
            todo = todo[: args.limit]
        if not todo:
            log.info("✅ 本轮没有待发送的 IM 房间 (全部已发)")
            return 0
        log.info("本轮 IM 招商 %d 个: %s", len(todo), ", ".join(r["nickname"] for r in todo))
        for idx, r in enumerate(todo, 1):
            key = r["wxid"]
            st = state.setdefault(key, {"wxid": key, "nickname": r["nickname"], "roomId": r["roomId"],
                                        "stage": "pending", "reason": "",
                                        "updated": time.strftime("%Y-%m-%d %H:%M:%S")})
            ok, reason = run_im_send(r["roomId"], text)
            st["stage"] = "im_sent" if ok else "failed"
            st["reason"] = "" if ok else reason
            st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_state(state)
            log.info("[%d/%d] %s: %s", idx, len(todo), r["nickname"],
                     "✅ IM 招商消息已发送" if ok else f"❌ 发送失败: {reason}")
        write_report(state, todo)
        log.info("🏁 IM 招商结束, 报告: %s", REPORT_FILE)
        return 0

    # IM 自动回复: 单轮扫描已招商房间, 达人新消息 -> rag 自动回复
    if args.stage == "reply":
        return run_reply(args)

    # 前置自检
    if args.stage in ("all", "scan"):
        if not check_wxshop_login():
            return 1
    if args.stage in ("all", "add", "send"):
        if not check_wechat():
            return 1
    if args.stage in ("all", "send") and args.watch:
        check_rag()

    # 阶段一: wxshop 找达人
    contacts_path = Path(args.contacts) if args.contacts else None
    if args.stage in ("scan", "all"):
        talents = WORK_DIR / "talents.jsonl"
        contacts = WORK_DIR / "contacts.jsonl"
        log.info("── 阶段一: wxshop 扫描达人 + 提取联系方式 ──")
        if not run_scan(talents, args.cat or None, args.max_pages):
            log.error("❌ daren-scan 失败")
            return 1
        if not backfill_room_ids(talents):
            log.error("❌ 没有可从 imUrl 提取的 roomId")
            return 1
        if not run_contact(talents, contacts):
            log.error("❌ daren-contact 失败 (可能命中每日提取上限)")
            return 1
        contacts_path = contacts
        log.info("✅ 阶段一完成: %s", contacts_path)

    if contacts_path is None:
        log.error("❌ 没有 contacts 来源 (需 --contacts 或完整 scan 流程)")
        return 1

    items = load_contacts(contacts_path)
    if not items:
        log.error("❌ contacts 里没有有效 wxId")
        return 1

    # 跳过已完成
    state = load_state()
    todo = [it for it in items if state.get(it["wxid"], {}).get("stage") not in STAGES_DONE]
    if args.limit and args.limit > 0:
        todo = todo[: args.limit]
    if not todo:
        log.info("✅ 本轮没有待处理 wxid (全部已完成或达上限)")
        return 0
    log.info("本轮待处理 %d 个: %s", len(todo), ", ".join(it["wxid"] for it in todo))

    # 阶段二/三: 逐个加好友 + 发招商
    for idx, it in enumerate(todo, 1):
        wxid, nick = it["wxid"], it["nickname"]
        log.info("══ [%d/%d] %s (%s) ══", idx, len(todo), nick, wxid)
        st = state.setdefault(wxid, {"wxid": wxid, "nickname": nick, "stage": "pending", "reason": "",
                                     "updated": time.strftime("%Y-%m-%d %H:%M:%S")})

        if args.stage in ("all", "add"):
            if st.get("stage") == "added":
                log.info("已加好友, 跳过 add")
            else:
                ok, reason = run_add_friend(wxid)
                st["stage"] = "added" if ok else "failed"
                st["reason"] = "" if ok else reason
                st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_state(state)
                if not ok:
                    log.error("加好友失败: %s", reason)
                    continue

        if args.stage in ("all", "send"):
            if st.get("stage") == "sent":
                log.info("已发消息, 跳过 send")
                continue
            ok, reason = run_send_message(wxid, text)
            st["stage"] = "sent" if ok else st.get("stage", "pending")
            st["reason"] = "" if ok else reason
            st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_state(state)
            if ok:
                log.info("✅ 招商消息已发送: %s", wxid)
            else:
                log.error("发送失败: %s", reason)

    done_count = sum(1 for it in items if state.get(it["wxid"], {}).get("stage") in STAGES_DONE)
    write_report(state, todo, done_count)
    log.info("🏁 编排结束, 报告: %s", REPORT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
