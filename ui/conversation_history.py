"""
ui/conversation_history.py — Conversation History Panel (Feature 17)
Searchable list of past prompts and AI responses.
"""

import tkinter as tk
from datetime import datetime
from typing import List, Optional, Tuple

import customtkinter as ctk


_BG     = "#0d1117"
_HDR_BG = "#161b22"
_FG     = "#e6edf3"
_MUTED  = "#8b949e"
_BLUE   = "#58a6ff"
_GREEN  = "#3fb950"
_SEL_BG = "#1f3a5f"


class ConversationEntry:
    def __init__(self, role: str, text: str, mode: str = "chat"):
        self.role = role
        self.text = text
        self.mode = mode
        self.timestamp = datetime.now().strftime("%H:%M:%S")

    def preview(self, max_len: int = 80) -> str:
        return self.text[:max_len] + ("..." if len(self.text) > max_len else "")


class ConversationHistory(ctk.CTkFrame):
    """
    Searchable history of all chat messages.
    Clicking a history entry copies the text to the chat input.
    """

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=_BG)
        self.app = app
        self._entries: List[ConversationEntry] = []
        self._filtered: List[ConversationEntry] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build()

    def _build(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=_HDR_BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header, text="🕐 History",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=12, pady=8)

        self._count = ctk.CTkLabel(
            header, text="", font=("Segoe UI", 10), text_color=_MUTED,
        )
        self._count.pack(side="right", padx=12)

        # Search bar
        search_frame = ctk.CTkFrame(self, fg_color=_BG)
        search_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=6)
        search_frame.grid_columnconfigure(0, weight=1)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ctk.CTkEntry(
            search_frame, placeholder_text="Search history...",
            textvariable=self._search_var,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            search_frame, text="Clear All", width=80,
            command=self.clear,
        ).grid(row=0, column=1)

        # History list
        self._list_frame = ctk.CTkScrollableFrame(self, fg_color=_BG)
        self._list_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self._list_frame.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(
            self._list_frame,
            text="No history yet.\nStart a conversation to see it here.",
            font=("Segoe UI", 11), text_color=_MUTED,
        )
        self._empty_label.pack(pady=40)

    def add_entry(self, role: str, text: str, mode: str = "chat") -> None:
        """Add a message to history."""
        entry = ConversationEntry(role=role, text=text, mode=mode)
        self._entries.append(entry)
        self._filter()
        self._update_count()

    def _filter(self) -> None:
        query = self._search_var.get().strip().lower()
        if query:
            self._filtered = [e for e in self._entries if query in e.text.lower()]
        else:
            self._filtered = list(self._entries)
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        for widget in self._list_frame.winfo_children():
            widget.destroy()

        if not self._filtered:
            ctk.CTkLabel(
                self._list_frame,
                text="No matching history." if self._search_var.get() else "No history yet.",
                font=("Segoe UI", 11), text_color=_MUTED,
            ).pack(pady=40)
            return

        for entry in reversed(self._filtered[-100:]):  # Show last 100
            self._add_entry_widget(entry)

    def _add_entry_widget(self, entry: ConversationEntry) -> None:
        frame = ctk.CTkFrame(
            self._list_frame, fg_color="#161b22", corner_radius=6,
            cursor="hand2",
        )
        frame.pack(fill="x", padx=2, pady=2)
        frame.grid_columnconfigure(1, weight=1)

        role_color = _BLUE if entry.role == "You" else _GREEN
        ctk.CTkLabel(
            frame,
            text=f"[{entry.timestamp}] {entry.role}",
            font=("Segoe UI", 9, "bold"),
            text_color=role_color,
            anchor="w",
        ).grid(row=0, column=0, padx=8, pady=(4, 0), sticky="w")

        mode_badge = "🤖" if entry.mode == "agent" else "💬"
        ctk.CTkLabel(frame, text=mode_badge, font=("Segoe UI", 9)).grid(row=0, column=1, sticky="e", padx=8)

        ctk.CTkLabel(
            frame, text=entry.preview(),
            font=("Segoe UI", 10), anchor="w",
            text_color=_FG, wraplength=300,
        ).grid(row=1, column=0, columnspan=2, padx=8, pady=(2, 6), sticky="ew")

        # Click to re-use
        def on_click(e=entry):
            self._reuse(e)
        frame.bind("<Button-1>", lambda ev, e=entry: on_click(e))

    def _reuse(self, entry: ConversationEntry) -> None:
        """Copy the entry text into the chat input."""
        if self.app and hasattr(self.app, "chat_panel"):
            chat = self.app.chat_panel
            if hasattr(chat, "input_box"):
                chat.input_box.delete(0, tk.END)
                chat.input_box.insert(0, entry.text[:200])

    def _update_count(self) -> None:
        self._count.configure(text=f"{len(self._entries)} messages")

    def clear(self) -> None:
        self._entries.clear()
        self._filtered.clear()
        self._rebuild_list()
        self._update_count()
