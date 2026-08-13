"""任务控制 — 启动/停止编排任务、自动回复一轮."""

from __future__ import annotations

import sys

import customtkinter as ctk

from client.views import UI_FONT

STAGE_CHOICES = ["all", "scan", "add", "send", "im"]


class ControlsView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build_form()
        self._build_status()
        self.prefill(self.app.cfg)

    # ── 构建 ────────────────────────────────────────────────
    def _build_form(self) -> None:
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(14, 7), pady=14)
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True, padx=(7, 14), pady=14)

        row = 0
        ctk.CTkLabel(left, text="任务参数", font=(UI_FONT, 14, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 8)); row += 1

        self._stage = self._combo(left, "阶段:", STAGE_CHOICES, row); row += 1
        self._limit = self._entry(left, "本轮处理数 limit:", "10", row); row += 1
        self._max_pages = self._entry(left, "扫描页数 max-pages:", "1", row); row += 1
        self._cat = self._entry(left, "达人类目 cat:", "", row); row += 1
        self._contacts = self._entry(left, "现成 contacts 文件:", "", row); row += 1

        ctk.CTkLabel(left, text="招商文案:", font=(UI_FONT, 13)).grid(
            row=row, column=0, sticky="nw", pady=(8, 0)); row += 1
        self._text = ctk.CTkTextbox(left, height=180, wrap="word", font=(UI_FONT, 13))
        self._text.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(4, 0)); row += 1
        left.grid_rowconfigure(row, weight=1)
        left.grid_columnconfigure(0, weight=0)
        left.grid_columnconfigure(1, weight=1)

        self._start_btn = ctk.CTkButton(right, text="启动任务", height=38,
                                        fg_color="#2f7bd9", hover_color="#2564b0",
                                        command=self._start)
        self._start_btn.pack(fill="x", pady=8)
        self._stop_btn = ctk.CTkButton(right, text="停止任务", height=38,
                                       fg_color="#c95050", hover_color="#a84040",
                                       state="disabled", command=self.app.stop_task)
        self._stop_btn.pack(fill="x", pady=8)
        self._reply_btn = ctk.CTkButton(right, text="自动回复一轮 (IM)", height=38,
                                        fg_color="#2ec5c5", hover_color="#1e8e8e",
                                        command=self._reply)
        self._reply_btn.pack(fill="x", pady=8)
        ctk.CTkLabel(right, text="", height=8).pack()
        self._status_label = ctk.CTkLabel(right, text="空闲", text_color="#9aa0a6",
                                          font=(UI_FONT, 13))
        self._status_label.pack(fill="x", pady=4)
        ctk.CTkLabel(right, text="提示: 阶段 all/send/im 需填写招商文案;\n"
                                  "scan 只扫描提取联系方式, 不发消息。",
                     text_color=("#6a6f76", "#8a8f96"), justify="left",
                     font=(UI_FONT, 12)).pack(fill="x", pady=(12, 4))

    def _build_status(self) -> None:
        pass  # 状态合并到右侧按钮区

    # ── 表单控件 ────────────────────────────────────────────
    def _combo(self, parent, label: str, values: list[str], row: int) -> ctk.CTkComboBox:
        ctk.CTkLabel(parent, text=label, font=(UI_FONT, 13)).grid(
            row=row, column=0, sticky="w", pady=4)
        cb = ctk.CTkComboBox(parent, values=values, state="readonly", width=240)
        cb.set(values[0])
        cb.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        return cb

    def _entry(self, parent, label: str, default: str, row: int) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=(UI_FONT, 13)).grid(
            row=row, column=0, sticky="w", pady=4)
        e = ctk.CTkEntry(parent, width=240)
        e.insert(0, default)
        e.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        return e

    # ── 动作 ────────────────────────────────────────────────
    def _num(self, entry: ctk.CTkEntry, default: int) -> int:
        try:
            return int(entry.get().strip())
        except ValueError:
            return default

    def _start(self) -> None:
        if self.app.worker.running:
            self.app.log("任务已在运行中, 无法重复启动")
            return
        stage = self._stage.get().strip() or "all"
        limit = self._num(self._limit, 10)
        max_pages = self._num(self._max_pages, 1)
        cat = self._cat.get().strip()
        contacts = self._contacts.get().strip()
        text = self._text.get("1.0", "end").strip()
        if stage in ("all", "send", "im") and not text:
            self.app.log("该阶段需要招商文案: 请在左侧填写或到「设置」保存")
            return
        args = ["-m", "recruit", "--stage", stage,
                "--limit", str(limit), "--max-pages", str(max_pages)]
        if cat:
            args += ["--cat", cat]
        if contacts:
            args += ["--contacts", contacts]
        if text:
            args += ["--text", text]
        self.app.start_task([sys.executable] + args)

    def _reply(self) -> None:
        if self.app.worker.running:
            self.app.log("任务已在运行中, 无法重复启动")
            return
        self.app.start_task([sys.executable, "recruit_orchestrator.py", "--stage", "reply"])

    # ── 状态更新 (由 app 转发 bridge 消息调用) ───────────────
    def set_status(self, status: dict) -> None:
        state = status.get("state")
        running = state in ("starting", "running", "stopping")
        self._start_btn.configure(state="disabled" if running else "normal")
        self._reply_btn.configure(state="disabled" if running else "normal")
        self._stop_btn.configure(state="normal" if state == "running" else "disabled")
        if state == "running":
            self._status_label.configure(
                text=f"运行中 (pid={status.get('pid')})", text_color="#3ddc84")
        elif state == "starting":
            self._status_label.configure(text="启动中…", text_color="#ffb84d")
        elif state == "stopping":
            self._status_label.configure(text="停止中…", text_color="#ff6b6b")
        elif state == "idle":
            code = status.get("exit_code")
            txt = f"已结束 (退出码 {code})" if code is not None else "空闲"
            self._status_label.configure(
                text=txt, text_color="#ff6b6b" if (code or 0) != 0 else "#9aa0a6")

    def set_exit(self, code: int) -> None:
        txt = f"任务已结束 (退出码 {code})"
        self._status_label.configure(
            text=txt, text_color="#ff6b6b" if code != 0 else "#3ddc84")

    # ── 配置预填 ────────────────────────────────────────────
    def prefill(self, cfg: dict) -> None:
        self._stage.set(cfg.get("stage", "all"))
        self._set_entry(self._limit, str(cfg.get("limit", 10)))
        self._set_entry(self._max_pages, str(cfg.get("max_pages", 1)))
        self._set_entry(self._cat, str(cfg.get("cat", "")))
        self._set_entry(self._contacts, str(cfg.get("contacts", "")))
        text = str(cfg.get("text", ""))
        if not text:
            text = _default_text()
        self._set_text(self._text, text)

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    @staticmethod
    def _set_text(box: ctk.CTkTextbox, value: str) -> None:
        box.delete("1.0", "end")
        box.insert("1.0", value)


def _default_text() -> str:
    """缺省文案: 从 wechat-friend-add/.env 的 RECRUIT_TEXT 读取."""
    try:
        from recruit.config import resolve_text
        return resolve_text("")
    except Exception:  # noqa: BLE001
        return ""
