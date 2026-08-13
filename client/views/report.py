"""报告查看 — 只读预览 recruit_report.md."""

from __future__ import annotations

import customtkinter as ctk

from client.views import MONO_FONT, UI_FONT


class ReportView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(top, text="报告文件:", font=(UI_FONT, 13)).pack(side="left")
        self._path = ctk.CTkLabel(top, text=str(self.app.report_file),
                                  text_color=("#6a6f76", "#9aa0a6"))
        self._path.pack(side="left", padx=8)
        ctk.CTkButton(top, text="刷新", width=90, command=self.refresh).pack(side="right")

        self._box = ctk.CTkTextbox(self, wrap="word", font=(MONO_FONT, 12))
        self._box.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def refresh(self) -> None:
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        p = self.app.report_file
        if p.exists():
            self._box.insert("1.0", p.read_text(encoding="utf-8", errors="replace"))
        else:
            self._box.insert("1.0", f"(报告文件不存在: {p})")
        self._box.configure(state="disabled")
