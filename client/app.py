"""主窗口 — 左导航 + 内容区 + 底部日志栏, 持有 worker/bridge."""

from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk

WORK_DIR = Path(__file__).resolve().parent.parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

from recruit.paths import CONTACTS_FILE, REPORT_FILE, STATE_FILE, TALENTS_FILE  # noqa: E402

from client import config_store  # noqa: E402
from client.bridge import QueueBridge  # noqa: E402
from client.worker import TaskWorker  # noqa: E402
from client.views import UI_FONT  # noqa: E402
from client.views.config import ConfigView  # noqa: E402
from client.views.controls import ControlsView  # noqa: E402
from client.views.dashboard import DashboardView  # noqa: E402
from client.views.data import DataView  # noqa: E402
from client.views.report import ReportView  # noqa: E402

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

NAV_ITEMS = [
    ("dashboard", "监控面板"),
    ("controls", "任务控制"),
    ("report", "报告"),
    ("data", "数据"),
    ("config", "设置"),
]


class RecruitApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("达人招商编排客户端")
        self.geometry("1180x760")
        self.minsize(980, 620)

        self.bridge = QueueBridge(self)
        self.worker = TaskWorker(self.bridge)
        self.cfg = config_store.load()
        self.state_file = STATE_FILE
        self.report_file = REPORT_FILE
        self.contacts_file = CONTACTS_FILE
        self.talents_file = TALENTS_FILE
        self.config_file = config_store.CONFIG_FILE

        self._build_sidebar()
        self._build_content()
        self._build_log_pane()

        self.bridge.register("log", self._on_log)
        self.bridge.register("status", self._on_status)
        self.bridge.register("exit", self._on_exit)

        self._current: str | None = None
        self.bridge.start()
        self._show("dashboard")
        self.after(300, lambda: self.log("客户端已就绪。点「任务控制」启动编排。"))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 布局 ────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=170, corner_radius=0)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        ctk.CTkLabel(side, text="达人招商编排", font=(UI_FONT, 15, "bold"),
                     text_color="#4aa3ff").pack(pady=(18, 16))

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        for key, label in NAV_ITEMS:
            btn = ctk.CTkButton(side, text=label, anchor="w", fg_color="transparent",
                                hover_color=("#e4e9f0", "#2a2d37"),
                                command=lambda k=key: self._show(k))
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = btn

        status_frame = ctk.CTkFrame(side, fg_color="transparent")
        status_frame.pack(side="bottom", fill="x", padx=12, pady=12)
        self._status_dot = ctk.CTkLabel(status_frame, text="○", font=(UI_FONT, 15),
                                        text_color="#9aa0a6")
        self._status_dot.pack(anchor="w")
        self._status_text = ctk.CTkLabel(status_frame, text="空闲", font=(UI_FONT, 12),
                                         text_color="#9aa0a6", wraplength=140)
        self._status_text.pack(anchor="w", pady=(2, 8))
        self._global_stop = ctk.CTkButton(status_frame, text="停止任务", height=30,
                                          fg_color="#c95050", hover_color="#a84040",
                                          state="disabled", command=self.stop_task)
        self._global_stop.pack(fill="x")

    def _build_content(self) -> None:
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(side="left", fill="both", expand=True, padx=14, pady=14)
        self._views = {
            "dashboard": DashboardView(self._content, app=self),
            "controls": ControlsView(self._content, app=self),
            "report": ReportView(self._content, app=self),
            "data": DataView(self._content, app=self),
            "config": ConfigView(self._content, app=self),
        }

    def _build_log_pane(self) -> None:
        frame = ctk.CTkFrame(self, height=170, corner_radius=0,
                             fg_color=("#eef2f7", "#191b22"))
        frame.pack(side="bottom", fill="x")
        frame.pack_propagate(False)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(header, text="日志", font=(UI_FONT, 12, "bold")).pack(side="left")
        ctk.CTkLabel(header, text="", font=(UI_FONT, 11)).pack(side="left", padx=8)
        ctk.CTkButton(header, text="清空", width=60, height=24, command=self.clear_log
                      ).pack(side="right")
        self._log_box = ctk.CTkTextbox(frame, height=150, wrap="word", font=("Consolas", 11))
        self._log_box.pack(fill="both", padx=10, pady=(2, 8))
        self._log_box.configure(state="disabled")
        self._log_lines = 0

    # ── 导航 ────────────────────────────────────────────────
    def _show(self, key: str) -> None:
        if self._current is not None:
            self._views[self._current].pack_forget()
        view = self._views[key]
        view.pack(fill="both", expand=True)
        self._current = key
        for k, btn in self._nav_btns.items():
            btn.configure(fg_color=("#dbe4f5", "#2a2d37") if k == key else "transparent")
        refresh = getattr(view, "refresh", None)
        if refresh:
            refresh()

    # ── 任务控制接口 (供 views 调用) ────────────────────────
    def start_task(self, cmd: list[str]) -> None:
        self.log(f"[任务] 启动: {' '.join(cmd)}")
        ok = self.worker.start(cmd, WORK_DIR, self.state_file)
        if not ok:
            self.log("[任务] 已在运行中, 无法重复启动")

    def stop_task(self) -> None:
        if self.worker.running:
            self.log("[任务] 正在停止 …")
        self.worker.stop()

    def log(self, msg: str) -> None:
        self.bridge.push("log", msg)

    def on_config_saved(self, cfg: dict) -> None:
        self.cfg = cfg
        self._views["controls"].prefill(cfg)
        self.log("[设置] 已保存到 client_config.json")

    # ── bridge 消息 ─────────────────────────────────────────
    def _on_log(self, line: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line + "\n")
        self._log_lines += 1
        if self._log_lines > 3000:
            self._log_box.delete("1.0", "2.0")
            self._log_lines -= 1
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _on_status(self, status: dict) -> None:
        state = status.get("state")
        if state == "idle":
            code = status.get("exit_code")
            txt = f"空闲 (退出码 {code})" if code is not None else "空闲"
            self._status_dot.configure(text="○", text_color="#9aa0a6")
            self._status_text.configure(text=txt)
            self._global_stop.configure(state="disabled")
        elif state == "running":
            self._status_dot.configure(text="●", text_color="#3ddc84")
            self._status_text.configure(text=f"运行中 pid={status.get('pid')}")
            self._global_stop.configure(state="normal")
        elif state == "starting":
            self._status_dot.configure(text="●", text_color="#ffb84d")
            self._status_text.configure(text="启动中…")
        elif state == "stopping":
            self._status_dot.configure(text="●", text_color="#ff6b6b")
            self._status_text.configure(text="停止中…")
        self._views["controls"].set_status(status)

    def _on_exit(self, code: int) -> None:
        self._views["controls"].set_exit(code)

    def clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._log_lines = 0

    def _on_close(self) -> None:
        self.worker.stop()
        self.bridge.stop()
        self.destroy()
