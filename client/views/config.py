"""设置 — 编辑招商文案与默认参数, 保存到 client_config.json."""

from __future__ import annotations

import customtkinter as ctk

from client import config_store
from client.views import UI_FONT

STAGE_CHOICES = ["all", "scan", "add", "send", "im"]


class ConfigView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build()
        self.prefill(self.app.cfg)

    def _build(self) -> None:
        ctk.CTkLabel(self, text="客户端默认设置",
                     font=(UI_FONT, 14, "bold")).pack(anchor="w", padx=14, pady=(14, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        form.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(form, text="默认阶段:", font=(UI_FONT, 13)).grid(
            row=row, column=0, sticky="w", pady=4); row += 1
        self._stage = ctk.CTkComboBox(form, values=STAGE_CHOICES, state="readonly", width=240)
        self._stage.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4); row += 1

        self._limit = self._row(form, row, "默认 limit:"); row += 1
        self._max_pages = self._row(form, row, "默认 max-pages:"); row += 1
        self._cat = self._row(form, row, "默认类目 cat:"); row += 1
        self._contacts = self._row(form, row, "默认 contacts 文件:"); row += 1

        ctk.CTkLabel(form, text="招商文案 (RECRUIT_TEXT):",
                     font=(UI_FONT, 13)).grid(row=row, column=0, sticky="nw", pady=(8, 0)); row += 1
        self._text = ctk.CTkTextbox(form, height=200, wrap="word", font=(UI_FONT, 13))
        self._text.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(4, 0)); row += 1
        form.grid_rowconfigure(row, weight=1)

        ctk.CTkButton(self, text="保存设置", height=36, fg_color="#2f7bd9",
                      hover_color="#2564b0", command=self._save).pack(fill="x", padx=14, pady=(0, 14))

    def _row(self, parent, row: int, label: str) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=(UI_FONT, 13)).grid(
            row=row, column=0, sticky="w", pady=4)
        e = ctk.CTkEntry(parent, width=240)
        e.grid(row=row, column=1, sticky="ew", pady=4)
        return e

    def _save(self) -> None:
        cfg = {
            "stage": self._stage.get().strip() or "all",
            "limit": self._int(self._limit, 10),
            "max_pages": self._int(self._max_pages, 1),
            "cat": self._cat.get().strip(),
            "contacts": self._contacts.get().strip(),
            "text": self._text.get("1.0", "end").strip(),
        }
        config_store.save(cfg)
        self.app.on_config_saved(cfg)

    @staticmethod
    def _int(entry: ctk.CTkEntry, default: int) -> int:
        try:
            return int(entry.get().strip())
        except ValueError:
            return default

    def prefill(self, cfg: dict) -> None:
        self._stage.set(cfg.get("stage", "all"))
        self._set(self._limit, str(cfg.get("limit", 10)))
        self._set(self._max_pages, str(cfg.get("max_pages", 1)))
        self._set(self._cat, str(cfg.get("cat", "")))
        self._set(self._contacts, str(cfg.get("contacts", "")))
        self._text.delete("1.0", "end")
        self._text.insert("1.0", str(cfg.get("text", "")))

    @staticmethod
    def _set(entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)
