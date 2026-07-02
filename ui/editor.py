import os
import re
import tkinter as tk
import customtkinter as ctk


class EditorPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="#0d1117")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.path = ""
        self._reload_timer = None
        self._dirty = False

        self.text_area = tk.Text(
            self,
            wrap="none",
            bg="#0d1117",
            fg="#e6edf3",
            insertbackground="white",
            undo=True,
            font=("Consolas", 12),
        )
        self.text_area.grid(row=0, column=0, sticky="nsew")
        self.text_area.bind("<Control-s>", self.save_current)
        self.text_area.bind("<KeyRelease>", self.on_key_release)
        self.text_area.bind("<FocusOut>", self.schedule_reload)
        self.text_area.bind("<Return>", self.on_return)
        self.text_area.bind("<KeyPress>", self.on_key_press)

        self.scroll_y = tk.Scrollbar(self, orient="vertical", command=self.text_area.yview)
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.text_area.configure(yscrollcommand=self.scroll_y.set)

        self.text_area.tag_configure("keyword", foreground="#60a5fa")
        self.text_area.tag_configure("string", foreground="#86efac")
        self.text_area.tag_configure("comment", foreground="#6b7280", font=("Consolas", 12, "italic"))
        self.text_area.tag_configure("number", foreground="#f9a8d4")
        self.text_area.tag_configure("matching", background="#1f2937")

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.text_area.configure(state=state)

    def set_text(self, content: str) -> None:
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", content)
        self._dirty = False
        self.highlight_syntax()

    def get_text(self) -> str:
        return self.text_area.get("1.0", tk.END)

    def get_selection(self) -> str:
        try:
            return self.text_area.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    def set_path(self, path: str) -> None:
        self.path = path

    def save_current(self, _event=None) -> None:
        self._dirty = False
        self.app.save_current_file()

    def on_key_release(self, _event=None) -> None:
        self._dirty = True
        self.schedule_reload()
        self.highlight_syntax()

    def on_key_press(self, event=None) -> None:
        if event and event.keysym in {"parenleft", "bracketleft", "braceleft", "quotedbl", "apostrophe"}:
            self.match_bracket(event)

    def on_return(self, _event=None) -> None:
        self.auto_indent()
        return "break"

    def match_bracket(self, event) -> None:
        if not event:
            return
        char_map = {"parenleft": "(", "bracketleft": "[", "braceleft": "{", "quotedbl": '"', "apostrophe": "'"}
        opening = char_map.get(event.keysym)
        if not opening:
            return
        self.text_area.insert(tk.INSERT, opening)

    def auto_indent(self) -> None:
        current_line = self.text_area.get("insert linestart", "insert lineend")
        indent = len(current_line) - len(current_line.lstrip(" "))
        self.text_area.insert(tk.INSERT, "\n" + " " * indent)

    def schedule_reload(self, _event=None) -> None:
        if self._reload_timer:
            self.after_cancel(self._reload_timer)
        self._reload_timer = self.after(500, self.auto_reload)

    def auto_reload(self) -> None:
        if self._dirty or not self.path or not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8", errors="ignore") as handle:
            current_content = handle.read()
        if current_content != self.get_text():
            self.set_text(current_content)

    def highlight_syntax(self) -> None:
        self.text_area.tag_remove("keyword", "1.0", tk.END)
        self.text_area.tag_remove("string", "1.0", tk.END)
        self.text_area.tag_remove("comment", "1.0", tk.END)
        self.text_area.tag_remove("number", "1.0", tk.END)

        content = self.get_text()
        keywords = {
            "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del",
            "elif", "else", "except", "False", "finally", "for", "from", "global", "if", "import",
            "in", "is", "lambda", "None", "nonlocal", "not", "or", "pass", "raise", "return",
            "True", "try", "while", "with", "yield"
        }

        for match in re.finditer(r"\b(?:" + "|".join(re.escape(word) for word in keywords) + r")\b", content):
            self.text_area.tag_add("keyword", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        for match in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', content):
            self.text_area.tag_add("string", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        for match in re.finditer(r"#.*", content):
            self.text_area.tag_add("comment", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        for match in re.finditer(r"\b\d+\b", content):
            self.text_area.tag_add("number", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
