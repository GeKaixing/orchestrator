"""数据浏览 — contacts/talents/state/config 文件只读预览."""

from __future__ import annotations

import json
from pathlib import Path

import customtkinter as ctk

from client.views import MONO_FONT, UI_FONT


class DataView(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._files: dict[str, Path] = {
            "contacts.jsonl": app.contacts_file,
            "talents.jsonl": app.talents_file,
            "recruit_state.json": app.state_file,
            "client_config.json": app.config_file,
        }

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(top, text="文件:", font=(UI_FONT, 13)).pack(side="left")
        self._file_var = ctk.StringVar(value="contacts.jsonl")
        self._combo = ctk.CTkComboBox(top, values=list(self._files), width=180,
                                      variable=self._file_var,
                                      command=lambda _: self.refresh())
        self._combo.pack(side="left", padx=8)
        self._count = ctk.CTkLabel(top, text="", text_color=("#6a6f76", "#9aa0a6"))
        self._count.pack(side="left", padx=8)
        ctk.CTkButton(top, text="刷新", width=90, command=self.refresh).pack(side="right")

        self._box = ctk.CTkTextbox(self, wrap="none", font=(MONO_FONT, 12))
        self._box.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def refresh(self) -> None:
        path = self._files.get(self._file_var.get())
        text, count = _read_text(path)
        self._count.configure(text=f"{count} 条记录")
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.insert("1.0", text)
        self._box.configure(state="disabled")


def _read_text(path: Path) -> tuple[str, int]:
    if not path.exists():
        return f"(文件不存在: {path})", 0
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"(读取失败: {e})", 0
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    count = len(lines)
    # JSONL: 每行一条记录; 单 JSON 对象: 显示键数/条数
    if path.name.endswith(".jsonl"):
        return raw, count
    if count == 1:
        try:
            obj = json.loads(lines[0])
            n = len(obj) if isinstance(obj, dict) else len(obj)
            return raw, n
        except Exception:  # noqa: BLE001
            return raw, count
    return raw, count
