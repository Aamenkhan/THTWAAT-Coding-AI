"""
ui/main_window.py — Main Application Window
Phase 3: switch_model() routes provider/model at runtime; grouped toolbar combo.
Phase 4: AgentPanel replaces inline AI Chat dock.
Phase 5: Pipeline stage rows + approval gate wired into AgentPanel.
Phase 6: open_settings() → SettingsDialog.
"""

import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from editor.code_editor import CodeEditor
from ui.toolbar import Toolbar
from ui.ai_worker import AIWorker
from ui.pipeline_worker import PipelineWorker
from ui.diff_viewer import DiffViewerDialog
from ui.workspace_search_panel import WorkspaceSearchPanel
from ui.agent_panel import AgentPanel
from ai.pipeline import PipelineRun, Stage
from ai.diff_engine import DiffEngine
from ai.tab_complete import InlineCompletionController

try:
    from ui.activity_panel import ActivityPanel
except ImportError:
    ActivityPanel = QtWidgets.QTextEdit        # type: ignore[misc]
try:
    from ui.pipeline_panel import PipelinePanel
except ImportError:
    PipelinePanel = QtWidgets.QTextEdit        # type: ignore[misc]
try:
    from ui.task_queue_panel import TaskQueuePanel
except ImportError:
    TaskQueuePanel = QtWidgets.QTextEdit       # type: ignore[misc]
try:
    from ui.conversation_history import ConversationHistoryPanel
except ImportError:
    ConversationHistoryPanel = QtWidgets.QTextEdit  # type: ignore[misc]


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
        self.attached_image_path: Optional[str] = None

        # Runtime state
        self.config: dict = {}
        self.provider_router = None
        self.diff_engine = DiffEngine()
        self._active_provider: str = "ollama"   # Phase 3: tracks current provider
        self._active_model: str = "qwen2.5-coder:3b"  # Phase 3: tracks current model

        self.file_icon_provider = QtWidgets.QFileIconProvider()

        self._build_ui()
        self._setup_status_bar()

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_config(self, config: dict) -> None:
        self.config = config
        model = config.get("model")
        if model:
            self.toolbar.set_model(model)

    # ── Phase 3: Runtime model/provider switch ────────────────────────────────

    def switch_model(self, provider: str, model_id: str) -> None:
        """
        Phase 3 — Runtime switch.
        Updates _active_provider, _active_model, and ProviderRouter primary.
        Does NOT write config.json and does NOT restart the application.
        """
        self._active_provider = provider
        self._active_model = model_id
        if self.provider_router:
            self.provider_router.set_primary(provider)
        self.update_model_status(model_id)

    def update_model_status(self, model_name: str) -> None:
        """Update the status-bar model label (single definition — Phase 3 fix)."""
        self.status_model.setText(f"Model: {model_name}")

    # ── Phase 6: Settings dialog ──────────────────────────────────────────────

    def open_settings(self) -> None:
        """Phase 6 — Open the Settings dialog."""
        try:
            from ui.settings_dialog import SettingsDialog
            dlg = SettingsDialog(self)
            dlg.exec()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, "Settings", f"Could not open settings:\n{exc}"
            )

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # CENTER: Editor
        self.central_editor = CodeEditor(self)
        self.central_editor.go_to_definition_requested.connect(self._on_go_to_definition)
        self.central_editor.rename_symbol_requested.connect(self._on_rename_symbol)
        self.central_editor.inline_completion_requested.connect(self._on_inline_completion_requested)
        self.setCentralWidget(self.central_editor)

        # LEFT: Project Explorer
        self.project_explorer = QtWidgets.QTreeWidget(self)
        self.project_explorer.setObjectName("ProjectExplorer")
        self.project_explorer.setHeaderHidden(True)
        self.project_explorer.setAlternatingRowColors(True)
        self.project_explorer.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self._populate_project_explorer()

        self.project_dock = QtWidgets.QDockWidget("Project Explorer", self)
        self.project_dock.setWidget(self.project_explorer)
        self.project_dock.setAllowedAreas(
            QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea
        )
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.project_dock)

        # LEFT: Workspace Search
        self.search_panel = WorkspaceSearchPanel(self)
        self.search_panel.set_project_dir(str(self.project_root))
        self.search_panel.result_selected.connect(self._on_search_result_selected)

        self.search_dock = QtWidgets.QDockWidget("Search", self)
        self.search_dock.setWidget(self.search_panel)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.search_dock)

        self.tabifyDockWidget(self.project_dock, self.search_dock)
        self.project_dock.raise_()

        # RIGHT: Agent Panel — Phase 4 (replaces inline AI Chat)
        self.agent_panel = AgentPanel(self)
        self.agent_panel.message_submitted.connect(self._on_agent_message_submitted)
        self.agent_panel.stop_requested.connect(self._on_stop_requested)
        self.agent_panel.approval_decided.connect(self._on_approval_decided)
        self.agent_panel.image_attached.connect(self._on_image_attached)

        self.chat_dock = QtWidgets.QDockWidget("Agent", self)
        self.chat_dock.setWidget(self.agent_panel)
        self.chat_dock.setAllowedAreas(
            QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea
        )
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.chat_dock)

        # BOTTOM-LEFT: Terminal / Problems / Output
        self.bottom_tabs = QtWidgets.QTabWidget(self)
        from ui.terminal_widget import TerminalWidget
        self.terminal_page = TerminalWidget(self.bottom_tabs)
        self.problems_page = QtWidgets.QTextEdit(self.bottom_tabs)
        self.problems_page.setPlainText("No problems detected.\n")
        self.problems_page.setReadOnly(True)
        self.output_page = QtWidgets.QTextEdit(self.bottom_tabs)
        self.output_page.setPlainText("Build output will appear here.\n")
        self.output_page.setReadOnly(True)
        self.bottom_tabs.addTab(self.terminal_page, "Terminal")
        self.bottom_tabs.addTab(self.problems_page, "Problems")
        self.bottom_tabs.addTab(self.output_page, "Output")

        self.workspace_dock = QtWidgets.QDockWidget("Workspace", self)
        self.workspace_dock.setWidget(self.bottom_tabs)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.workspace_dock)

        # BOTTOM-RIGHT: Agent Panels (Pipeline, Activity, Task Queue, History)
        self.agent_tabs = QtWidgets.QTabWidget(self)
        self.pipeline_panel = (
            PipelinePanel(None, self)
            if PipelinePanel is not QtWidgets.QTextEdit
            else PipelinePanel(self.agent_tabs)
        )
        self.activity_panel = (
            ActivityPanel()
            if callable(ActivityPanel)
            else ActivityPanel(self.agent_tabs)
        )
        self.task_queue_panel = (
            TaskQueuePanel()
            if callable(TaskQueuePanel)
            else TaskQueuePanel(self.agent_tabs)
        )
        self.history_panel = (
            ConversationHistoryPanel()
            if callable(ConversationHistoryPanel)
            else ConversationHistoryPanel(self.agent_tabs)
        )

        self.agent_tabs.addTab(self.pipeline_panel, "Pipeline")
        self.agent_tabs.addTab(self.activity_panel, "Activity")
        self.agent_tabs.addTab(self.task_queue_panel, "Tasks")
        self.agent_tabs.addTab(self.history_panel, "History")

        self.agent_dock = QtWidgets.QDockWidget("Agent Panels", self)
        self.agent_dock.setWidget(self.agent_tabs)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.agent_dock)

        self.splitDockWidget(self.workspace_dock, self.agent_dock, QtCore.Qt.Horizontal)

        # TOP: Toolbar
        self.toolbar = Toolbar(self)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.toolbar)
        self.toolbar_buttons = self.toolbar.buttons

        self.setDockNestingEnabled(True)

    def _setup_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")

        self.status_ollama = QtWidgets.QLabel("● Disconnected")
        self.status_ollama.setStyleSheet("color: red; font-weight: bold;")
        self.statusBar().addPermanentWidget(self.status_ollama)

        self.status_model = QtWidgets.QLabel("Model: Qwen")
        self.statusBar().addPermanentWidget(self.status_model)

        self.status_git = QtWidgets.QLabel("Git: main")
        self.statusBar().addPermanentWidget(self.status_git)

        self.status_cursor = QtWidgets.QLabel("Ln 1, Col 1")
        self.statusBar().addPermanentWidget(self.status_cursor)

        self.central_editor.cursorPositionChanged.connect(self._update_cursor_status)

    def _update_cursor_status(self) -> None:
        cursor = self.central_editor.textCursor()
        line = cursor.blockNumber() + 1
        col  = cursor.columnNumber() + 1
        self.status_cursor.setText(f"Ln {line}, Col {col}")

    # ── Project Explorer ──────────────────────────────────────────────────────

    _EXPLORER_IGNORE = {
        "build", "dist", "config_backups", "__pycache__", "node_modules",
        ".venv", "venv", ".mypy_cache", ".pytest_cache", ".tox",
        "crash_reports",
    }

    def _populate_project_explorer(self) -> None:
        self.project_explorer.clear()
        if hasattr(self, "search_panel"):
            self.search_panel.set_project_dir(str(self.project_root))
        if not self.project_root.exists():
            return

        root_item = QtWidgets.QTreeWidgetItem([str(self.project_root.name)])
        root_item.setIcon(0, self.file_icon_provider.icon(QtCore.QFileInfo(str(self.project_root))))
        root_item.setData(0, QtCore.Qt.UserRole, str(self.project_root))
        root_item.setExpanded(True)
        self.project_explorer.addTopLevelItem(root_item)

        def _add_children(parent_item, path: Path):
            try:
                children = sorted(path.iterdir())
            except PermissionError:
                return
            for child in children:
                if child.name.startswith(".") or child.name in self._EXPLORER_IGNORE:
                    continue
                item = QtWidgets.QTreeWidgetItem([child.name])
                item.setIcon(0, self.file_icon_provider.icon(QtCore.QFileInfo(str(child))))
                item.setData(0, QtCore.Qt.UserRole, str(child))
                parent_item.addChild(item)
                if child.is_dir():
                    _add_children(item, child)

        _add_children(root_item, self.project_root)
        self.project_explorer.expandToDepth(1)

    def _on_tree_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        path = item.data(0, QtCore.Qt.UserRole)
        if path and os.path.isfile(path):
            self.open_file(path)

    # ── AgentPanel signal receivers (Phase 4) ─────────────────────────────────

    def _on_image_attached(self, path: str) -> None:
        """Store attached image path (sent by AgentPanel image_attached signal)."""
        self.attached_image_path = path

    def _on_stop_requested(self) -> None:
        """Stop the running AIWorker when user presses ⏹."""
        if hasattr(self, "ai_worker") and self.ai_worker.isRunning():
            self.ai_worker.stop()

    def _on_approval_decided(self, approved: bool) -> None:
        """
        Phase 5 — Handle pipeline approval gate decision from AgentPanel.
        Hides the gate and calls pipeline_worker.resume(approved).
        """
        self.agent_panel.hide_approval_gate()
        if hasattr(self, "pipeline_worker"):
            if approved and self.current_path:
                self.central_editor.open_file(self.current_path)
            self.pipeline_worker.resume(approved)
            if not approved:
                self.statusBar().showMessage("Pipeline cancelled.")

    def _on_agent_message_submitted(self, text: str) -> None:
        """
        Phase 4 — Handle a user message from the AgentPanel input row.
        Routes to AIWorker via ProviderRouter. model_map kept as fallback (Phase 3 Step 4).
        """
        if not text and not getattr(self, "attached_image_path", None):
            return

        # Phase 3: read actual model ID from toolbar UserRole data
        model = self.toolbar.get_model_id()

        # Vision capability check
        if getattr(self, "attached_image_path", None):
            vision_capable = any(m in model.lower() for m in [
                "llava", "minicpm-v", "llama3.2-vision",
                "gpt-4o", "gemini-1.5-pro", "claude-3-5-sonnet",
            ])
            if self._active_provider == "ollama" and not vision_capable:
                QtWidgets.QMessageBox.warning(
                    self, "Vision Not Supported",
                    "Current model doesn't support images — switch to a vision-capable model"
                )
                return

        # Render user message in AgentPanel stream
        self.agent_panel.append_user(text)
        if getattr(self, "attached_image_path", None):
            self.agent_panel.append_system(
                f"[Attached Image: {Path(self.attached_image_path).name}]"
            )
        self.attached_image_path = None
        self.agent_panel._img_preview.hide()

        if not self.provider_router:
            self.agent_panel.append_error("Provider Router not initialized.")
            return

        # model_map kept as fallback — Phase 3 Step 4: do NOT remove
        model_map = {
            "Ollama (Qwen)": "qwen2.5-coder:3b",
            "Claude":        "claude-3-5-sonnet-20241022",
            "OpenAI":        "gpt-4o",
            "Gemini":        "gemini-1.5-pro",
        }
        mapped_model = model_map.get(model, model)

        # Build context from open file
        system_prompt = "You are THTWAAT AI IDE Assistant."
        if self.current_path and os.path.exists(self.current_path):
            content = Path(self.current_path).read_text(encoding="utf-8")
            system_prompt += (
                f"\n\nContext file '{Path(self.current_path).name}':\n```\n{content}\n```"
            )

        self.agent_panel.set_stop_visible(True)
        self.agent_panel.set_input_enabled(False)
        self.agent_panel.set_badge("● Generating…", "#d29922")
        self.agent_panel.append_assistant_start()

        self.ai_worker = AIWorker(
            self.provider_router, text, mapped_model, system_prompt, self
        )
        self.ai_worker.token_received.connect(self._on_ai_token)
        self.ai_worker.finished.connect(self._on_ai_finished)
        self.ai_worker.error_occurred.connect(self._on_ai_error)
        self.ai_worker.start()

    # Keep legacy _submit_chat as a shim for code that calls it directly
    def _submit_chat(self) -> None:
        """Legacy shim — forwards to _on_agent_message_submitted."""
        text = self.agent_panel.input.text().strip()
        self._on_agent_message_submitted(text)

    def _on_ai_token(self, token: str) -> None:
        self.agent_panel.append_token(token)

    def _on_ai_finished(self) -> None:
        self.agent_panel.end_assistant()
        self._cleanup_ai_worker()

    def _on_ai_error(self, err: str) -> None:
        self.agent_panel.end_assistant()
        self.agent_panel.append_error(err)
        self._cleanup_ai_worker()

    def _cleanup_ai_worker(self) -> None:
        self.agent_panel.set_stop_visible(False)
        self.agent_panel.set_input_enabled(True)
        self.agent_panel.set_badge("● Ready", "#3fb950")
        self.agent_panel.input.setFocus()

    # ── File attach (kept for toolbar compatibility) ───────────────────────────

    def attach_image(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Attach Image", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self.attached_image_path = path
            pix = QtGui.QPixmap(path).scaledToHeight(100, QtCore.Qt.SmoothTransformation)
            self.agent_panel._img_preview.setPixmap(pix)
            self.agent_panel._img_preview.setToolTip(path)
            self.agent_panel._img_preview.show()

    # ── File operations ───────────────────────────────────────────────────────

    def new_file(self) -> None:
        if self.central_editor.document().isModified():
            reply = QtWidgets.QMessageBox.question(
                self, "Unsaved Changes",
                "Save changes before creating new file?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.save_current_file()
            elif reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                return

        self.current_path = None
        self.central_editor.set_text("")
        self.statusBar().showMessage("New file created")

    def open_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Open Folder", str(self.project_root)
        )
        if folder:
            self.project_root = Path(folder)
            self._populate_project_explorer()
            self.statusBar().showMessage(f"Opened {folder}")

    def save_current_file(self) -> None:
        if not self.current_path:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save File",
                str(self.project_root / "untitled.py"),
                "Python Files (*.py)",
            )
            if not path:
                return
            self.current_path = path
        Path(self.current_path).write_text(self.central_editor.text(), encoding="utf-8")
        self.statusBar().showMessage(f"Saved {self.current_path}")
        self.central_editor.document().setModified(False)

    def open_file(self, path: str) -> None:
        if not os.path.exists(path):
            return
        if self.central_editor.document().isModified():
            reply = QtWidgets.QMessageBox.question(
                self, "Unsaved Changes",
                "Save changes before opening another file?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.save_current_file()
            elif reply == QtWidgets.QMessageBox.StandardButton.Cancel:
                return
        self.current_path = path
        self.central_editor.open_file(path)
        self.statusBar().showMessage(f"Opened {path}")

    # ── Code actions ───────────────────────────────────────────────────────────

    def run_code(self) -> None:
        if self.current_path and self.current_path.endswith(".py"):
            self.statusBar().showMessage(f"Running {self.current_path}")
            self.bottom_tabs.setCurrentIndex(0)
            cmd = f'python "{self.current_path}"'
            active_term = self.terminal_page.get_current_terminal()
            if active_term and active_term.process.state() == QtCore.QProcess.Running:
                cursor = active_term.textCursor()
                cursor.movePosition(QtGui.QTextCursor.End)
                active_term.setTextCursor(cursor)
                active_term.insertPlainText(cmd + "\n")
                active_term.prompt_position = active_term.textCursor().position()
                active_term.expected_echo = cmd + "\n"
                active_term.process.write(cmd.encode("utf-8") + b"\r\n")
        else:
            self.statusBar().showMessage("No runnable Python file selected")

    def ai_edit(self) -> None:
        if not self.current_path:
            self.statusBar().showMessage("Open a file to edit first")
            return

        prompt, ok = QtWidgets.QInputDialog.getText(
            self, "AI Edit", "What would you like to change?"
        )
        if not ok or not prompt:
            return

        self.agent_panel.append_user(f"Edit: {prompt}")
        self.agent_panel.append_system("Starting edit pipeline…")

        cursor = self.central_editor.textCursor()
        selected_text = cursor.selectedText().replace("\u2029", "\n")

        if selected_text:
            context = f"Selected code in {self.current_path}:\n```\n{selected_text}\n```"
        else:
            code = self.central_editor.text()
            context = f"File content of {self.current_path}:\n```\n{code}\n```"

        goal = f"Edit {self.current_path}: {prompt}\n\n{context}"
        self.current_pipeline = PipelineRun(goal=goal, run_id="edit-1")

        self.pipeline_worker = PipelineWorker(self.current_pipeline, self.diff_engine, self)
        self.pipeline_worker.stage_changed.connect(self._on_pipeline_stage)
        self.pipeline_worker.finished.connect(self._on_pipeline_finished)
        self.pipeline_worker.review_requested.connect(self._on_pipeline_review_requested)
        self.pipeline_worker.start()

    def explain(self) -> None:
        if not self.current_path:
            self.statusBar().showMessage("Open a file to explain first")
            return

        cursor = self.central_editor.textCursor()
        selected_text = cursor.selectedText().replace("\u2029", "\n")
        if selected_text:
            code_context = f"Selected code in {self.current_path}:\n```\n{selected_text}\n```"
            msg = "Explain the selected code."
        else:
            code_context = f"File content of {self.current_path}:\n```\n{self.central_editor.text()}\n```"
            msg = "Explain this file."

        self.agent_panel.append_user(msg)

        if not self.provider_router:
            self.agent_panel.append_error("Provider Router not initialized.")
            return

        # Phase 3: get_model_id() returns real model ID; model_map kept as fallback
        model = self.toolbar.get_model_id()
        model_map = {
            "Ollama (Qwen)": "qwen2.5-coder:3b",
            "Claude":        "claude-3-5-sonnet-20241022",
            "OpenAI":        "gpt-4o",
            "Gemini":        "gemini-1.5-pro",
        }
        mapped_model = model_map.get(model, model)

        system_prompt = f"You are THTWAAT AI IDE Assistant.\n\nContext:\n{code_context}"

        self.agent_panel.set_stop_visible(True)
        self.agent_panel.set_input_enabled(False)
        self.agent_panel.set_badge("● Generating…", "#d29922")
        self.agent_panel.append_assistant_start()

        self.ai_worker = AIWorker(
            self.provider_router, "Explain this code in detail.",
            mapped_model, system_prompt, self
        )
        self.ai_worker.token_received.connect(self._on_ai_token)
        self.ai_worker.finished.connect(self._on_ai_finished)
        self.ai_worker.error_occurred.connect(self._on_ai_error)
        self.ai_worker.start()

    def optimize(self) -> None:
        if not self.current_path:
            self.statusBar().showMessage("Open a file to optimize first")
            return

        warn = QtWidgets.QMessageBox(self)
        warn.setWindowTitle("⚠️ Experimental Feature")
        warn.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        warn.setText(
            "<b>This feature is experimental.</b><br><br>"
            "The AI Optimize pipeline may produce <b>incorrect, trivial, or "
            "unrelated changes</b> depending on the model and file complexity.<br><br>"
            "<b>Always review every change carefully before accepting.</b><br><br>"
            "<i>Note: changes must be accepted or rejected together — "
            "individual file-level reject is not yet available.</i>"
        )
        warn.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Ok
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        warn.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Ok)
        if warn.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        self.agent_panel.append_user("Optimize current file")
        self.agent_panel.append_system("Starting optimization pipeline…")

        goal = f"Optimize {self.current_path}"
        code = self.central_editor.text()
        if code:
            goal += f"\n\nFile content of {self.current_path}:\n```\n{code}\n```"
        self.current_pipeline = PipelineRun(goal=goal, run_id="opt-1")

        self.pipeline_worker = PipelineWorker(self.current_pipeline, self.diff_engine, self)
        self.pipeline_worker.stage_changed.connect(self._on_pipeline_stage)
        self.pipeline_worker.finished.connect(self._on_pipeline_finished)
        self.pipeline_worker.review_requested.connect(self._on_pipeline_review_requested)
        self.pipeline_worker.start()

    # ── Pipeline handlers (Phase 5) ────────────────────────────────────────────

    def _on_pipeline_stage(self, stage_name: str, progress: int) -> None:
        """Phase 5 — Show stage progress in AgentPanel stream and status bar."""
        self.statusBar().showMessage(f"Pipeline: {stage_name} ({progress}%)")
        self.agent_panel.append_pipeline_stage(stage_name, "active", progress)

    def _on_pipeline_review_requested(self) -> None:
        """
        Phase 5 — Show DiffViewerDialog for reviewing changes.
        Result propagates back via pipeline_worker.resume().
        """
        dialog = DiffViewerDialog(self.diff_engine, self)
        accepted = bool(dialog.exec())

        if accepted:
            self.agent_panel.append_system("Changes accepted — continuing pipeline…")
            if self.current_path:
                self.central_editor.open_file(self.current_path)
            self.pipeline_worker.resume(True)
        else:
            self.agent_panel.append_system("Changes rejected — pipeline stopped.")
            self.statusBar().showMessage("Pipeline cancelled.")
            self.pipeline_worker.resume(False)

    def _on_pipeline_finished(self, success: bool, message: str) -> None:
        self.statusBar().showMessage(message)
        if success:
            self.agent_panel.append_pipeline_stage("Complete", "done", 100)
        else:
            self.agent_panel.append_error(message)

    # ── Symbol navigation ──────────────────────────────────────────────────────

    def _on_search_result_selected(self, path: str, line: int) -> None:
        self.open_file(path)
        self.central_editor.goto_line(line)

    def _on_go_to_definition(self, word: str) -> None:
        if not hasattr(self, "search_panel") or not self.search_panel.search_backend:
            return
        result = self.search_panel.search_backend.go_to_definition(word)
        if result:
            self.open_file(result.path)
            self.central_editor.goto_line(result.line)
            self.statusBar().showMessage(f"Jumped to definition of {word}")
        else:
            self.statusBar().showMessage(f"Definition not found for {word}")

    def _on_rename_symbol(self, old_name: str, new_name: str) -> None:
        if not hasattr(self, "search_panel") or not self.search_panel.search_backend:
            return
        self.statusBar().showMessage(f"Renaming {old_name} to {new_name}...")
        diffs = self.search_panel.search_backend.rename_symbol(
            old_name, new_name, dry_run=True
        )
        if not diffs:
            self.statusBar().showMessage(f"No occurrences of {old_name} found.")
            return
        self.diff_engine.clear()
        for path, diff_text in diffs.items():
            from ai.diff_engine import PendingEdit
            self.diff_engine.propose_edit(path, diff_text, f"Rename {old_name} to {new_name}")
        dialog = DiffViewerDialog(self.diff_engine, self)
        if dialog.exec():
            self.statusBar().showMessage(f"Renamed {old_name} to {new_name} successfully.")
            if self.current_path:
                self.central_editor.open_file(self.current_path)
        else:
            self.statusBar().showMessage("Rename cancelled.")

    def _on_inline_completion_requested(self, prefix: str, suffix: str) -> None:
        if not self.provider_router:
            return
            
        # Initialize controller if needed
        if not hasattr(self, "inline_controller"):
            self.inline_controller = InlineCompletionController(self.provider_router, self)
            self.inline_controller.token_received.connect(self.central_editor.show_ghost_text)

        model = self.toolbar.get_model_id()
        model_map = {
            "Ollama (Qwen)": "qwen2.5-coder:3b",
            "Claude":        "claude-3-5-sonnet-20241022",
            "OpenAI":        "gpt-4o",
            "Gemini":        "gemini-flash-latest",
            "Gemini Pro":    "gemini-2.0-flash",
            "Gemini Flash":  "gemini-flash-latest",
        }
        mapped_model = model_map.get(model, model)

        indexer = None
        if hasattr(self, "agent_panel") and self.agent_panel.agent:
            indexer = self.agent_panel.agent.workspace.indexer

        self.inline_controller.stream_completion(prefix, suffix, mapped_model, indexer)

    # ── Git ────────────────────────────────────────────────────────────────────

    def git(self) -> None:
        if not self.project_root:
            self.statusBar().showMessage("Open a project folder first")
            return
        
        self.agent_panel.append_user("Git Status")
        import subprocess
        try:
            res = subprocess.run(["git", "status", "-s"], cwd=str(self.project_root), capture_output=True, text=True)
            if not res.stdout.strip():
                self.agent_panel.append_system("Git Status: Working tree clean.")
            else:
                self.agent_panel.append_system(f"Git Status — Pending changes:\n{res.stdout}")
        except Exception as e:
            self.agent_panel.append_error(f"Git error: {e}")

    def _submit_chat_with_message(self, title: str, message: str) -> None:
        """Legacy helper — kept for compatibility."""
        self.agent_panel.append_system(f"[{title}] {message}")

    # ── Window events ──────────────────────────────────────────────────────────

    def closeEvent(self, event: QtCore.QEvent) -> None:
        event.accept()
