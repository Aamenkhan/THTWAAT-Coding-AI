import os
import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from editor.code_editor import CodeEditor
from ui.toolbar import Toolbar


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("THTWAAT Coding AI")
        self.resize(1400, 900)
        self.setObjectName("MainWindow")

        self.project_root = Path(__file__).resolve().parent.parent / "projects"
        self.current_path: Optional[str] = None
        self.open_files: dict[str, str] = {}
        self.toolbar_buttons: list[QtWidgets.QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.central_editor = CodeEditor(self)
        self.setCentralWidget(self.central_editor)

        self.project_explorer = QtWidgets.QTreeWidget(self)
        self.project_explorer.setObjectName("ProjectExplorer")
        self.project_explorer.setHeaderHidden(True)
        self.project_explorer.setAlternatingRowColors(True)
        self.project_explorer.setColumnCount(1)
        self.project_explorer.setHeaderLabel("Project")
        self._populate_project_explorer()
        project_dock = QtWidgets.QDockWidget("Project Explorer", self)
        project_dock.setWidget(self.project_explorer)
        project_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, project_dock)

        self.chat_panel = QtWidgets.QWidget(self)
        chat_layout = QtWidgets.QVBoxLayout(self.chat_panel)
        self.chat_output = QtWidgets.QTextEdit(self.chat_panel)
        self.chat_output.setReadOnly(True)
        self.chat_output.setPlaceholderText("AI chat will appear here.")
        self.chat_input = QtWidgets.QLineEdit(self.chat_panel)
        self.chat_input.setPlaceholderText("Ask the assistant...")
        self.chat_input.returnPressed.connect(self._submit_chat)
        chat_layout.addWidget(self.chat_output)
        chat_layout.addWidget(self.chat_input)
        chat_dock = QtWidgets.QDockWidget("AI Chat", self)
        chat_dock.setWidget(self.chat_panel)
        chat_dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, chat_dock)

        self.bottom_tabs = QtWidgets.QTabWidget(self)
        terminal_page = QtWidgets.QTextEdit(self.bottom_tabs)
        terminal_page.setPlainText("Terminal ready.\n")
        problems_page = QtWidgets.QTextEdit(self.bottom_tabs)
        problems_page.setPlainText("No problems detected.\n")
        output_page = QtWidgets.QTextEdit(self.bottom_tabs)
        output_page.setPlainText("Build output will appear here.\n")
        self.bottom_tabs.addTab(terminal_page, "Terminal")
        self.bottom_tabs.addTab(problems_page, "Problems")
        self.bottom_tabs.addTab(output_page, "Output")
        bottom_dock = QtWidgets.QDockWidget("Workspace", self)
        bottom_dock.setWidget(self.bottom_tabs)
        bottom_dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, bottom_dock)

        self.toolbar = Toolbar(self)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.toolbar)
        self.toolbar_buttons = self.toolbar.buttons

        self.setDockNestingEnabled(True)
        self.statusBar().showMessage("Ready")

    def _populate_project_explorer(self) -> None:
        root_item = QtWidgets.QTreeWidgetItem([str(self.project_root.name)])
        root_item.setExpanded(True)
        self.project_explorer.addTopLevelItem(root_item)
        for child in sorted(self.project_root.iterdir()):
            if child.name.startswith("."):
                continue
            item = QtWidgets.QTreeWidgetItem([child.name])
            root_item.addChild(item)
        self.project_explorer.expandAll()

    def _submit_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_output.append(f"> {text}\n")
        self.chat_output.append("Assistant: I can help with this workspace once the AI backend is wired in.\n")
        self.chat_input.clear()

    def new_file(self) -> None:
        self.current_path = None
        self.central_editor.set_text("")

    def open_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Folder", str(self.project_root))
        if folder:
            self.project_root = Path(folder)
            self._populate_project_explorer()
            self.statusBar().showMessage(f"Opened {folder}")

    def save_current_file(self) -> None:
        if not self.current_path:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save File", str(self.project_root / "untitled.py"), "Python Files (*.py)")
            if not path:
                return
            self.current_path = path
        Path(self.current_path).write_text(self.central_editor.text(), encoding="utf-8")
        self.statusBar().showMessage(f"Saved {self.current_path}")

    def open_file(self, path: str) -> None:
        if os.path.exists(path):
            self.current_path = path
            self.central_editor.open_file(path)
            self.statusBar().showMessage(f"Opened {path}")

    def run_code(self) -> None:
        if self.current_path and self.current_path.endswith(".py"):
            self.statusBar().showMessage(f"Running {self.current_path}")
            self.bottom_tabs.setCurrentIndex(0)
            terminal_page = self.bottom_tabs.widget(0)
            if isinstance(terminal_page, QtWidgets.QTextEdit):
                terminal_page.append(f"$ python {self.current_path}\n")
        else:
            self.statusBar().showMessage("No runnable Python file selected")

    def ai_edit(self) -> None:
        self._submit_chat_with_message("AI Edit", "The editor action is ready for the next integration step.")

    def explain(self) -> None:
        self._submit_chat_with_message("Explain", "The explain action is ready for the next integration step.")

    def optimize(self) -> None:
        self._submit_chat_with_message("Optimize", "The optimize action is ready for the next integration step.")

    def git(self) -> None:
        self._submit_chat_with_message("Git", "Git workflow hooks are ready for the next integration step.")

    def _submit_chat_with_message(self, title: str, message: str) -> None:
        self.chat_output.append(f"[{title}] {message}\n")

    def closeEvent(self, event: QtCore.QEvent) -> None:
        event.accept()

    def run(self) -> None:
        self.show()
        if QtWidgets.QApplication.instance() is not None:
            QtWidgets.QApplication.instance().exec()
