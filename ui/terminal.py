import subprocess
import threading
import tkinter as tk
import customtkinter as ctk


class TerminalPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="#161b22")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._process = None
        self._thread = None

        self.top_bar = ctk.CTkFrame(self, fg_color="#161b22")
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.clear_button = ctk.CTkButton(self.top_bar, text="Clear", command=self.clear)
        self.clear_button.grid(row=0, column=0, padx=6, pady=6)
        self.cancel_button = ctk.CTkButton(self.top_bar, text="Cancel", command=self.cancel_process, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=6, pady=6)

        self.command_entry = ctk.CTkEntry(self, placeholder_text="Enter a command")
        self.command_entry.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="ew")
        self.command_entry.bind("<Return>", lambda _event=None: self.run_command(self.command_entry.get()))
        self.run_button = ctk.CTkButton(self, text="Run", command=lambda: self.run_command(self.command_entry.get()))
        self.run_button.grid(row=1, column=1, padx=(0, 10), pady=(0, 6))

        self.output = tk.Text(self, bg="#0d1117", fg="#e6edf3", font=("Consolas", 10))
        self.output.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.output.insert(tk.END, "Offline terminal ready.\n")


class TerminalPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="#161b22")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._process = None
        self._thread = None

        self.top_bar = ctk.CTkFrame(self, fg_color="#161b22")
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.clear_button = ctk.CTkButton(self.top_bar, text="Clear", command=self.clear)
        self.clear_button.grid(row=0, column=0, padx=6, pady=6)
        self.cancel_button = ctk.CTkButton(self.top_bar, text="Cancel", command=self.cancel_process, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=6, pady=6)

        self.command_entry = ctk.CTkEntry(self, placeholder_text="Enter a command")
        self.command_entry.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="ew")
        self.command_entry.bind("<Return>", lambda _event=None: self.run_command(self.command_entry.get()))
        self.run_button = ctk.CTkButton(self, text="Run", command=lambda: self.run_command(self.command_entry.get()))
        self.run_button.grid(row=1, column=1, padx=(0, 10), pady=(0, 6))

        self.output = tk.Text(self, bg="#0d1117", fg="#e6edf3", font=("Consolas", 10))
        self.output.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.output.insert(tk.END, "Offline terminal ready.\n")

    def clear(self) -> None:
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, "Offline terminal ready.\n")

    def cancel_process(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self.cancel_button.configure(state="disabled")

    def run_command(self, command: str) -> None:
        if not command.strip():
            return
        if self._process and self._process.poll() is None:
            return
        self.output.insert(tk.END, f"> {command}\n")
        self.output.see(tk.END)
        self.cancel_button.configure(state="normal")

        def worker() -> None:
            try:
                self._process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.app.project_root,
                    bufsize=1,
                )
                for line in self._process.stdout or []:
                    self.output.after(0, lambda text=line: self.output.insert(tk.END, text))
                    self.output.after(0, lambda: self.output.see(tk.END))
                return_code = self._process.wait()
                self.output.after(0, lambda: self.output.insert(tk.END, f"\n[Process finished with code {return_code}]\n"))
            except Exception as exc:
                error_text = str(exc)
                self.output.after(0, lambda err=error_text: self.output.insert(tk.END, err))
            finally:
                self.output.after(0, lambda: self.cancel_button.configure(state="disabled"))
                self.output.after(0, lambda: self.output.see(tk.END))

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
