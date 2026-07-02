import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk
import markdown2
import pyperclip


class ChatPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, width=420, fg_color="#11151f")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._stop_generation = threading.Event()
        self._generation_thread = None

        title = ctk.CTkLabel(self, text="AI Chat", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, padx=12, pady=(10, 6), sticky="w")

        self.chat_box = tk.Text(self, bg="#0d1117", fg="#e6edf3", wrap="word", font=("Segoe UI", 11))
        self.chat_box.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="nsew")
        self.chat_box.tag_configure("role", font=("Segoe UI", 10, "bold"))
        self.chat_box.tag_configure("code", font=("Consolas", 10), foreground="#86efac")

        bottom = ctk.CTkFrame(self, fg_color="#11151f")
        bottom.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self.input_box = ctk.CTkEntry(bottom, placeholder_text="Ask the AI to explain, fix, or create...")
        self.input_box.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.input_box.bind("<Return>", self.send_message)

        self.send_btn = ctk.CTkButton(bottom, text="Send", command=self.send_message)
        self.send_btn.grid(row=0, column=1, padx=(0, 6))

        self.stop_btn = ctk.CTkButton(bottom, text="Stop", command=self.stop_generation, state="disabled")
        self.stop_btn.grid(row=0, column=2)

        self.copy_btn = ctk.CTkButton(self, text="Copy Code", command=self.copy_selected_code, state="disabled")
        self.copy_btn.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="w")

    def append_message(self, role: str, message: str) -> None:
        self.chat_box.insert(tk.END, f"{role}:\n", "role")
        self._insert_markdown(message)
        self.chat_box.insert(tk.END, "\n\n")
        self.chat_box.see(tk.END)

    def append_stream(self, chunk: str) -> None:
        self.chat_box.insert(tk.END, chunk)
        self.chat_box.see(tk.END)

    def _insert_markdown(self, message: str) -> None:
        lines = message.splitlines() or [message]
        in_code = False
        code_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                if in_code:
                    self.chat_box.insert(tk.END, "\n".join(code_lines) + "\n", "code")
                    code_lines = []
                    in_code = False
                else:
                    in_code = True
                    self.chat_box.insert(tk.END, "\n")
                continue
            if in_code:
                code_lines.append(line)
            else:
                self.chat_box.insert(tk.END, line + "\n")
        if in_code and code_lines:
            self.chat_box.insert(tk.END, "\n".join(code_lines) + "\n", "code")

    def set_generating(self, generating: bool) -> None:
        state = "disabled" if generating else "normal"
        self.input_box.configure(state=state)
        self.send_btn.configure(state=state)
        self.stop_btn.configure(state="normal" if generating else "disabled")
        self.copy_btn.configure(state=state)
        self.app.toolbar.set_state(not generating)
        self.app.editor_panel.set_enabled(not generating)

    def stop_generation(self) -> None:
        self._stop_generation.set()

    def copy_selected_code(self) -> None:
        selected = self.chat_box.get("sel.first", "sel.last")
        if selected:
            pyperclip.copy(selected)
            messagebox.showinfo("Copy", "Selected text copied to clipboard")

    def send_message(self, _event=None) -> None:
        if self._generation_thread and self._generation_thread.is_alive():
            return
        text = self.input_box.get().strip()
        if not text:
            return
        self.input_box.delete(0, tk.END)
        self.append_message("You", text)
        self.append_message("AI", "")
        self._stop_generation = threading.Event()
        self.set_generating(True)

        def worker() -> None:
            try:
                if text.lower().startswith("create project"):
                    prompt = text[len("create project"):].strip()
                    self.app.generate_project(prompt)
                    self.chat_box.after(0, self.set_generating, False)
                    return

                if text.lower().startswith("edit files"):
                    parts = text[len("edit files"):].strip()
                    edits = {}
                    for entry in parts.split(";"):
                        if "|" not in entry:
                            continue
                        path, content = entry.split("|", 1)
                        edits[path.strip()] = content.strip()
                    if edits:
                        self.app.preview_file_edits(edits)
                        self.chat_box.after(0, self.set_generating, False)
                        return

                if text.lower().startswith("create file"):
                    parts = text.split("|", 1)
                    if len(parts) == 2:
                        path = parts[0].split("create file", 1)[1].strip()
                        content = parts[1].strip()
                        self.app.agent.create_file(path, content)
                        self.app.refresh_project()
                        self.chat_box.after(0, self.append_message, "AI", f"Created file: {path}")
                        self.chat_box.after(0, self.set_generating, False)
                        return

                context_text = None
                if self.app.current_path:
                    with open(self.app.current_path, "r", encoding="utf-8", errors="ignore") as handle:
                        context_text = handle.read()
                if self.app.project_index and not context_text:
                    context_text = self.app.project_index.build_context(text)
                if self.app.plugin_manager:
                    text = self.app.plugin_manager.run_plugins(text, app=self.app)
                chunks = self.app.agent.stream_chat(text, context=context_text, stop_event=self._stop_generation)
                for chunk in chunks:
                    if self._stop_generation.is_set():
                        break
                    self.chat_box.after(0, lambda value=chunk: self.append_stream(value))
            except Exception as exc:
                error_text = str(exc)
                self.chat_box.after(0, lambda err=error_text: self.append_message("AI", f"Error: {err}"))
            finally:
                self.chat_box.after(0, self.set_generating, False)

        self._generation_thread = threading.Thread(target=worker, daemon=True)
        self._generation_thread.start()
