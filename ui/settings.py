import customtkinter as ctk
from tkinter import messagebox


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="#11151f")
        self.app = app
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Settings", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkLabel(self, text="Model").grid(row=1, column=0, padx=12, sticky="w")
        self.model_var = ctk.StringVar(value=self.app.config.get("model", "qwen2.5-coder:3b"))
        self.model_dropdown = ctk.CTkOptionMenu(self, values=["qwen2.5-coder:3b", "llama3.2", "phi3"], variable=self.model_var)
        self.model_dropdown.grid(row=2, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkLabel(self, text="Theme").grid(row=3, column=0, padx=12, sticky="w")
        self.theme_var = ctk.StringVar(value=self.app.config.get("theme", "dark"))
        self.theme_dropdown = ctk.CTkOptionMenu(self, values=["dark", "light"], variable=self.theme_var)
        self.theme_dropdown.grid(row=4, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkLabel(self, text="Recent workspaces").grid(row=5, column=0, padx=12, sticky="w")
        self.recent_var = ctk.StringVar(value="\n".join(self.app.config.get("recent_projects", [])[:5]))
        ctk.CTkLabel(self, textvariable=self.recent_var, justify="left", anchor="w").grid(row=6, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkButton(self, text="Apply", command=self.apply).grid(row=7, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkButton(self, text="Git Status", command=self.show_git_status).grid(row=8, column=0, padx=12, pady=(0, 6), sticky="w")
        ctk.CTkButton(self, text="Git Commit", command=self.commit_changes).grid(row=9, column=0, padx=12, pady=(0, 6), sticky="w")
        ctk.CTkButton(self, text="Create Branch", command=self.create_branch).grid(row=10, column=0, padx=12, pady=(0, 6), sticky="w")

    def apply(self) -> None:
        self.app.set_model(self.model_var.get())
        self.app.config["theme"] = self.theme_var.get()
        self.app.config["recent_projects"] = self.app.config.get("recent_projects", [])[:8]
        self.app.save_current_file()
        messagebox.showinfo("Settings", "Settings applied")

    def show_git_status(self) -> None:
        messagebox.showinfo("Git Status", self.app.git_status())

    def commit_changes(self) -> None:
        messagebox.showinfo("Git Commit", self.app.git_commit("updated via AI IDE"))

    def create_branch(self) -> None:
        messagebox.showinfo("Git Branch", self.app.switch_branch("feature/ai-ide"))
