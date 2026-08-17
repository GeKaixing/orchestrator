"""Hermes Agent — 通用 LLM 能力 (本机 hermes CLI) + 知识库问答 (hermes 无工具合成).

与 rag (向量检索) 不同, 本 agent 提供两类能力:
  - ask   : 任意 prompt 问答/任务 (招商文案生成、话术改写、资料整理…),
            通过本机 `hermes chat -q '<prompt>' -Q` 调用 Hermes Agent (私有能力)。
  - query : 知识库问答 — 由本模块在 orchestrator 侧只读 C:\\Users\\admin\\wiki
            检索相关片段注入 prompt, 再调 hermes chat 无工具合成 (-t "");
            Hermes 只看到注入的知识库片段, 无法读取知识库以外的内容。

依赖: 本机已安装 hermes CLI (shutil.which("hermes"))。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import get_logger
from ..paths import WIKI_DIR
from .base import AgentResult, BaseAgent, fail, ok

log = get_logger("agents.hermes")

_DEFAULT_TIMEOUT = 600  # hermes agent 会话可能跑几十秒到几分钟
_QUERY_BANNER = "session_id:"  # stderr 里的会话信息, 非错误

# ── 知识库检索 (query 专用, 只读 WIKI_DIR) ─────────────────────────
# 只认 H1/H2 切段: H3 是列表/子标题, 若也切段会把 产品矩阵 这类 H2 段切成空壳
# (H2 下全是 H3 时正文为空), 产品列表散落进低分小段, 检索答不全。
_HEADING_RE = re.compile(r"^#{1,2}\s+(.*)$")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TAG_RE = re.compile(r"tags:\s*\[([^\]]*)\]")
_KB_SKIP = {".obsidian", "node_modules", "raw", "_archive", ".git"}
# 导航/日志类文件不是知识: 检索时排除, 否则查询原文被写进 log.md 后会以满分污染召回
_KB_SKIP_FILES = {"log.md", "index.md", "SCHEMA.md"}


@dataclass
class KBSection:
    page: str
    title: str
    heading: str
    text: str
    tags: list[str] = field(default_factory=list)


def _kb_normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"[`*_#>\[\](){}~!|]", " ", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _kb_bigrams(text: str) -> set[str]:
    chars = _CJK_RE.findall(text)
    return {a + b for a, b in zip(chars, chars[1:])}


def _kb_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text))


def _kb_frontmatter(raw: str) -> dict[str, Any]:
    m = _FM_RE.match(raw)
    if not m:
        return {}
    fm: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        if key == "tags":
            t = _TAG_RE.search(line)
            tags = t.group(1).split(",") if t else ([value] if value else [])
            fm[key] = [x.strip().strip('"') for x in tags if x.strip()]
        else:
            fm[key] = value
    return fm


def _kb_iter(root: Path) -> list[KBSection]:
    """读知识库所有 md (跳过 raw/ 素材等), 按标题切段."""
    if not root.is_dir():
        return []
    out: list[KBSection] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(part in _KB_SKIP for part in rel.parts):
            continue
        if p.name in _KB_SKIP_FILES:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = _kb_frontmatter(raw)
        body = _FM_RE.sub("", raw)
        title = fm.get("title") or p.stem
        tags = fm.get("tags") or []
        cur_heading = ""
        cur_lines: list[str] = []
        for line in body.splitlines():
            h = _HEADING_RE.match(line)
            if h:
                if cur_lines and "\n".join(cur_lines).strip():
                    out.append(KBSection(rel.as_posix(), title, cur_heading,
                                         "\n".join(cur_lines).strip(), tags))
                cur_heading = h.group(1).strip()
                cur_lines = []
            else:
                cur_lines.append(line)
        if cur_lines and "\n".join(cur_lines).strip():
            out.append(KBSection(rel.as_posix(), title, cur_heading,
                                 "\n".join(cur_lines).strip(), tags))
    return out


def _kb_score(query: str, sec: KBSection) -> float:
    q_norm = _kb_normalize(query)
    q_bigrams = _kb_bigrams(q_norm)
    q_chars = set(_CJK_RE.findall(q_norm))
    q_words = _kb_words(q_norm)
    if not (q_bigrams or q_chars or q_words):
        return 0.0
    s_norm = _kb_normalize(f"{sec.title} {sec.heading} {sec.text}")
    s_bigrams = _kb_bigrams(s_norm)
    s_chars = set(_CJK_RE.findall(s_norm))
    s_words = _kb_words(s_norm)

    def ratio(hit: int, total: int) -> float:
        return hit / total if total else 0.0

    bigram_r = ratio(len(q_bigrams & s_bigrams), len(q_bigrams))
    char_r = ratio(len(q_chars & s_chars), len(q_chars))
    word_r = ratio(len(q_words & s_words), len(q_words))
    exact = 5.0 if q_norm and q_norm in s_norm else 0.0
    title_boost = 2.0 if q_norm and q_norm in _kb_normalize(sec.title) else 0.0
    # 小节标题/页面标题与查询的 bigram 重叠加成: 打破"概述"类无差别同分 (tie 按文件名序,
    # 曾把 产品矩阵 段挤出 top-5, 导致"有哪些产品"答不全)。关键词标题小节优先浮出。
    head_hit = ratio(len(q_bigrams & _kb_bigrams(_kb_normalize(sec.heading))), len(q_bigrams))
    ttl_hit = ratio(len(q_bigrams & _kb_bigrams(_kb_normalize(sec.title))), len(q_bigrams))
    head_boost = 6.0 * head_hit + 3.0 * ttl_hit
    return 3.0 * bigram_r + 2.0 * char_r + 1.0 * word_r + exact + title_boost + head_boost


def _kb_snippet(sec: KBSection, query: str, width: int = 1200) -> str:
    text = sec.text.replace("\n", " ").strip() or sec.title
    q_norm = _kb_normalize(query)
    idx = text.find(q_norm)
    if idx < 0:
        for ch in _CJK_RE.findall(query):
            i = text.find(ch)
            if i >= 0:
                idx = i
                break
    if idx < 0:
        return text[:width]
    start = max(0, idx - 40)
    seg = text[start:start + width]
    return ("…" if start > 0 else "") + seg + ("…" if start + width < len(text) else "")


def _kb_retrieve(question: str, root: Path, limit: int = 5) -> list[KBSection]:
    sections = _kb_iter(root)
    if not sections:
        return []
    scored = sorted(((s, _kb_score(question, s)) for s in sections),
                    key=lambda x: x[1], reverse=True)
    return [s for s, sc in scored if sc > 0][:limit]


class HermesAgent(BaseAgent):
    name = "hermes"

    # ── helpers ─────────────────────────────────────────────
    @staticmethod
    def _hermes_bin() -> str | None:
        return shutil.which("hermes")

    def _chat(self, prompt: str, params: dict[str, Any]) -> AgentResult:
        bin = self._hermes_bin()
        if not bin:
            return fail("hermes CLI 未安装 (PATH 中找不到 hermes)")
        prompt = (prompt or "").strip()
        if not prompt:
            return fail("prompt 不能为空")

        cmd = [bin, "chat", "-q", prompt, "-Q"]
        if params.get("model"):
            cmd += ["-m", str(params["model"])]
        if params.get("max_turns"):
            cmd += ["--max-turns", str(int(params["max_turns"]))]
        if params.get("skills"):
            cmd += ["-s", ",".join(str(s) for s in params["skills"])]
        # toolsets: 传入字符串启用限定工具集; 传空串 "" 禁用全部工具 (知识库问答用)
        if "toolsets" in params:
            cmd += ["-t", str(params["toolsets"])]
        base_dir = params.get("base_dir") or params.get("cwd")
        cwd = str(base_dir) if base_dir and os.path.isdir(str(base_dir)) else None

        timeout = float(params.get("timeout") or _DEFAULT_TIMEOUT)
        started = time.time()
        log.info("hermes chat (timeout=%.0fs, cwd=%s): %s", timeout, cwd, prompt[:120])
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            log.error("hermes chat 超时 (>%.0fs)", timeout)
            return fail(f"hermes 调用超时 (>{timeout:.0f}s)")
        except Exception as e:  # noqa: BLE001
            log.error("hermes chat 执行异常: %s", e)
            return fail(f"hermes 调用异常: {e}")

        elapsed = time.time() - started
        reply = (proc.stdout or "").strip()
        log.info("hermes chat 完成 rc=%s 耗时%.0fs 输出%d字", proc.returncode, elapsed, len(reply))
        if proc.returncode != 0 or not reply:
            err = (proc.stderr or "").strip()
            # 过滤已知噪音行, 保留真正的错误信息
            tail = "\n".join(
                l for l in err.splitlines()
                if l.strip() and not l.startswith(_QUERY_BANNER)
            )[-500:]
            return fail(f"hermes 无输出 (rc={proc.returncode}): {tail or '未知错误'}")
        return ok({"reply": reply, "elapsed_s": round(elapsed, 1)})

    # ── BaseAgent ───────────────────────────────────────────
    def health(self) -> dict:
        bin = self._hermes_bin()
        if not bin:
            return {"ok": False, "detail": "hermes CLI 未安装 (PATH 中找不到 hermes)"}
        try:
            proc = subprocess.run([bin, "--version"], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  timeout=30)
            if proc.returncode == 0:
                ver = (proc.stdout or proc.stderr or "").strip().splitlines()
                detail = f"hermes 可用 ({ver[0] if ver else bin})"
                if WIKI_DIR.is_dir():
                    detail += f"; 知识库 {WIKI_DIR}"
                else:
                    detail += f"; ⚠ 知识库目录不存在: {WIKI_DIR}"
                return {"ok": True, "detail": detail}
            return {"ok": False, "detail": f"hermes --version 失败 (rc={proc.returncode})"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"hermes 探测异常: {e}"}

    def run(self, action: str, **params: Any) -> AgentResult:
        if action in ("ask", "chat", "task"):
            # 通用问答/任务: params.prompt 或 params.question
            prompt = params.get("prompt") or params.get("question")
            return self._chat(str(prompt), params)
        if action == "query":
            # 知识库问答: orchestrator 侧只读 WIKI_DIR 检索片段注入, hermes CLI 无工具合成.
            # 检索只读知识库目录; 合成走 hermes chat -t "" (工具全禁用),
            # Hermes 无法读取知识库以外的任何内容, 且生成质量高于裸 API 直连。
            question = (params.get("question") or params.get("prompt") or "").strip()
            if not question:
                return fail("问题不能为空")
            root = Path(params.get("base_dir") or WIKI_DIR)
            limit = int(params.get("limit") or 5)
            top = _kb_retrieve(question, root, limit)
            if not top:
                return ok({"reply": f"知识库中未找到与“{question}”相关的内容。",
                           "sources": []})
            passages = "\n\n".join(
                f"[{i + 1}] 《{s.title}》{(' · ' + s.heading) if s.heading else ''}\n"
                f"{_kb_snippet(s, question)}"
                for i, s in enumerate(top)
            )
            sources = [{"title": s.heading or s.title, "path": s.page, "tags": s.tags}
                       for s in top]
            prompt = (
                "你是公司知识库问答助手。以下是从本地知识库检索到的相关资料片段。\n"
                "请只依据这些资料回答问题，不要编造、不要使用资料之外的信息；\n"
                "资料不足时如实说明「资料中未找到」。用简洁中文分点回答，不要在开头复述问题。\n\n"
                f"相关资料：\n{passages}\n\n"
                f"问题：{question}\n\n"
                "请依据资料回答，用简洁中文，不要加「来源」字样，不要复述问题。"
            )
            res = self._chat(prompt, {**params, "toolsets": "", "base_dir": None})
            if not res["success"]:
                return res
            reply = res["data"].get("reply", "")
            refs = [s.page for s in top]
            return ok({"reply": reply + (f"\n\n来源：{'、'.join(refs)}" if refs else ""),
                       "sources": sources})
        return fail(f"未知动作: {action}")


agent = HermesAgent()
