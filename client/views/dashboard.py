"""监控面板 — 统计卡片 + 达人状态表 + 环境自检."""

from __future__ import annotations

import threading

import customtkinter as ctk

from client.worker import snapshot_state
from client.views import MONO_FONT, STAGE_COLORS, STAGE_LABELS, STAGE_ORDER, UI_FONT

CARD_DEFS = [
    ("total", "达人总数", "#4aa3ff"),
    ("pending", "待处理", "#9aa0a6"),
    ("added", "已加好友", "#7c9ff2"),
    ("sent", "已发文案", "#3ddc84"),
    ("im_sent", "IM已发", "#2ec5c5"),
    ("failed", "失败", "#ff6b6b"),
]

CHECKS = [
    ("检查微信", "wechat"),
    ("检查 wxshop 登录", "wxshop"),
    ("检查 rag", "rag"),
]


class DashboardView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._cards: dict[str, ctk.CTkLabel] = {}
        self._checks: dict[str, bool] = {}
        self._auto_refresh = True
        self._last_sig: tuple | None = None

        self._build_cards()
        self._build_preflight()
        self._build_toolbar()
        self._build_table()

        self.app.bridge.register("state", self._on_state)
        self.app.bridge.register("check_result", self._on_check_result)

    # ── 构建 ────────────────────────────────────────────────
    def _build_cards(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(14, 6))
        for i, (key, label, color) in enumerate(CARD_DEFS):
            row.grid_columnconfigure(i, weight=1, uniform="cards")
            card = ctk.CTkFrame(row, fg_color=("#f1f4f9", "#1e2029"), corner_radius=8)
            card.grid(row=0, column=i, padx=5, pady=4, sticky="ew")
            ctk.CTkLabel(card, text=label, font=(UI_FONT, 12),
                         text_color=("#6a6f76", "#9aa0a6")).pack(pady=(8, 0))
            val = ctk.CTkLabel(card, text="0", font=(UI_FONT, 24, "bold"), text_color=color)
            val.pack(pady=(0, 8))
            self._cards[key] = val

    def _build_preflight(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(row, text="环境自检:", font=(UI_FONT, 13)).pack(side="left", padx=(0, 8))
        self._preflight_result = ctk.CTkLabel(row, text="", text_color=("#6a6f76", "#9aa0a6"))
        self._preflight_result.pack(side="left", padx=8)
        for label, kind in CHECKS:
            ctk.CTkButton(row, text=label, width=120, height=26,
                          command=lambda k=kind, l=label: self._run_check(l, k)
                          ).pack(side="right", padx=4)

    def _build_toolbar(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(row, text="阶段过滤:", font=(UI_FONT, 13)).pack(side="left")
        self._filter = ctk.CTkComboBox(row, values=["全部"] + STAGE_ORDER, width=130,
                                        state="readonly", command=lambda _: self.refresh())
        self._filter.set("全部")
        self._filter.pack(side="left", padx=(4, 14))
        self._auto_switch = ctk.CTkSwitch(row, text="运行中自动刷新",
                                          command=self._toggle_auto, progress_color="#3ddc84")
        self._auto_switch.select()
        self._auto_switch.pack(side="left")
        ctk.CTkButton(row, text="手动刷新", width=90, command=self.refresh).pack(side="left", padx=10)

    def _build_table(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(4, 0))
        bold = (UI_FONT, 12, "bold")
        hdr = [
            ("微信号", 170), ("昵称", 130), ("阶段", 90),
            ("更新时间", 150), ("备注", 40),
        ]
        for i, (txt, w) in enumerate(hdr):
            kwargs = {"font": bold, "anchor": "w"}
            if w:
                kwargs["width"] = w
            ctk.CTkLabel(header, text=txt, **kwargs).grid(row=0, column=i, sticky="w", padx=8)
        header.grid_columnconfigure(4, weight=1)
        self._body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=14, pady=(6, 14))

    # ── 数据刷新 ────────────────────────────────────────────
    def _toggle_auto(self) -> None:
        self._auto_refresh = bool(self._auto_switch.get())
        if self._auto_refresh:
            self.refresh()

    def refresh(self) -> None:
        self._apply(snapshot_state(self.app.state_file))

    def _on_state(self, snap: dict) -> None:
        if self._auto_refresh:
            self._apply(snap)

    def _apply(self, snap: dict) -> None:
        self._update_cards(snap.get("stats") or {})
        self._render_rows(snap.get("rows") or [], self._filter.get())

    def _update_cards(self, stats: dict) -> None:
        self._cards["total"].configure(text=str(sum(stats.values())))
        for key in ("pending", "added", "sent", "im_sent", "failed"):
            self._cards[key].configure(text=str(stats.get(key, 0)))

    def _render_rows(self, rows: list[dict], stage_filter: str) -> None:
        if stage_filter and stage_filter != "全部":
            rows = [r for r in rows if r["stage"] == stage_filter]
        sig = (len(rows), tuple(sorted(r["stage"] for r in rows)))
        if sig == self._last_sig:
            return
        self._last_sig = sig
        for child in self._body.winfo_children():
            child.destroy()
        if not rows:
            ctk.CTkLabel(self._body, text="(暂无数据)", text_color="#9aa0a6").pack(pady=20)
            return
        for r in rows:
            self._add_row(r)

    def _add_row(self, r: dict) -> None:
        stage = r["stage"]
        color = STAGE_COLORS.get(stage, "#9aa0a6")
        label = STAGE_LABELS.get(stage, stage)
        rowf = ctk.CTkFrame(self._body, fg_color=("#f8fafc", "#23252e"), corner_radius=6)
        rowf.pack(fill="x", padx=2, pady=2)
        fields = [
            (r["wxid"], "#ffffff", 0, 170),
            (r["nickname"], "#ffffff", 1, 130),
            (label, color, 2, 90),
            (r["updated"], "#9aa0a6", 3, 150),
            (r["reason"], "#9aa0a6", 4, 40),
        ]
        for text, tc, col, _w in fields:
            ctk.CTkLabel(rowf, text=text, font=(MONO_FONT if col == 0 else UI_FONT, 12),
                         text_color=tc, anchor="w").grid(row=0, column=col, sticky="w", padx=8, pady=4)
        rowf.grid_columnconfigure(4, weight=1)

    # ── 环境自检 ────────────────────────────────────────────
    def _run_check(self, label: str, kind: str) -> None:
        self._preflight_result.configure(text=f"{label} …")
        threading.Thread(target=self._do_check, args=(label, kind), daemon=True).start()

    def _do_check(self, label: str, kind: str) -> None:
        try:
            from recruit.services import wechat, wxshop
            fn = {"wechat": wechat.check_wechat, "wxshop": wxshop.check_login,
                  "rag": wechat.check_rag}[kind]
            ok = bool(fn())
        except Exception as e:  # noqa: BLE001
            ok = False
            self.app.bridge.push("log", f"[自检] {label} 异常: {e}")
        self.app.bridge.push("log", f"[自检] {label}: {'通过' if ok else '失败'}")
        self.app.bridge.push("check_result", {"label": label, "ok": ok})

    def _on_check_result(self, payload: dict) -> None:
        self._checks[payload["label"]] = bool(payload["ok"])
        parts = [f"{l}: {'通过' if ok else '失败'}" for l, ok in self._checks.items()]
        self._preflight_result.configure(text="  ·  ".join(parts))
