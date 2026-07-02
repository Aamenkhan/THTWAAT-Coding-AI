import os
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
import customtkinter as ctk


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, width=260, fg_color="#0d1117")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        title = ctk.CTkLabel(self, text="Project Explorer", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")

        self.project_label = ctk.CTkLabel(self, text=self.app.project_root, wraplength=220, justify="left")
        self.project_label.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")

        self.open_button = ctk.CTkButton(self, text="Open Folder", command=self.choose_folder)
        self.open_button.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="ew")

        self.search_entry = ctk.CTkEntry(self, placeholder_text="Search files")
        self.search_entry.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="ew")
        self.search_entry.bind("<Return>", self.search_project)

        self.search_button = ctk.CTkButton(self, text="Search", command=self.search_project)
        self.search_button.grid(row=4, column=0, padx=10, pady=(0, 6), sticky="ew")

        self.outline_label = ctk.CTkLabel(self, text="Outline", font=("Segoe UI", 12, "bold"))
        self.outline_label.grid(row=5, column=0, padx=10, pady=(0, 6), sticky="w")
        self.outline_box = tk.Listbox(self, bg="#161b22", fg="#e6edf3", highlightthickness=0, height=4)
        self.outline_box.grid(row=6, column=0, padx=10, pady=(0, 6), sticky="ew")

        self.tree = ttk.Treeview(self, show="tree")
        self.tree.grid(row=7, column=0, padx=10, pady=8, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-Button-1>", self.on_double_click)

        self.recent_label = ctk.CTkLabel(self, text="Recent Projects", font=("Segoe UI", 12, "bold"))
        self.recent_label.grid(row=8, column=0, padx=10, pady=(0, 6), sticky="w")
        self.recent_projects = tk.Listbox(self, bg="#161b22", fg="#e6edf3", highlightthickness=0, height=4)
        self.recent_projects.grid(row=9, column=0, padx=10, pady=(0, 6), sticky="ew")
        self.recent_projects.bind("<<ListboxSelect>>", self.open_recent_project)

        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.project_label.configure(text=self.app.project_root)
        self.recent_projects.delete(0, tk.END)
        for project in self.app.config.get("recent_projects", [])[:5]:
            self.recent_projects.insert(tk.END, project)
        if not os.path.isdir(self.app.project_root):
            return
        root_node = self.tree.insert("", "end", text=os.path.basename(self.app.project_root), open=True)
        self._populate_tree(root_node, self.app.project_root)

    def _populate_tree(self, parent_node: str, directory: str) -> None:
        entries = sorted(os.listdir(directory))
        for entry in entries:
            if entry in {".git", "__pycache__", "venv", ".venv", "build"}:
                continue
            path = os.path.join(directory, entry)
            if os.path.isdir(path):
                child = self.tree.insert(parent_node, "end", text=entry, values=(path,))
                self._populate_tree(child, path)
            else:
                self.tree.insert(parent_node, "end", text=entry, values=(path,))

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.app.project_root)
        if folder:
            self.app.set_project_root(folder)

    def search_project(self, _event=None) -> None:
        query = self.search_entry.get().strip()
        if not query:
            return
        results = self.app.project_index.search(query, self.app.project_root)
        if not results:
            return
        self.app.chat_panel.append_message("AI", f"Found {len(results)} matching files for '{query}'.")
        for result in results[:5]:
            self.app.chat_panel.append_message("AI", result["path"])

    def on_select(self, _event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if values:
            path = values[0]
            if os.path.isfile(path):
                self.app.open_file(path)

    def on_double_click(self, _event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if values:
            path = values[0]
            if os.path.isfile(path):
                self.app.open_file(path)

    def update_outline(self, path: str) -> None:
        if not os.path.exists(path):
            return
        outline = self.app.project_index.get_outline(path)
        self.outline_box.delete(0, tk.END)
        for item in outline:
            self.outline_box.insert(tk.END, f"{item['type']} {item['name']} @ line {item['line']}")

    def open_recent_project(self, _event) -> None:
        selection = self.recent_projects.curselection()
        if not selection:
            return
        project = self.recent_projects.get(selection[0])
        if os.path.isdir(project):
            self.app.set_project_root(project)

    def destroy(self):
        super().destroy()
