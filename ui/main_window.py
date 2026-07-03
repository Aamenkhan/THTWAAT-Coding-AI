import os
import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from editor.code_editor import CodeEditor
from ui.toolbar import Toolbar
from ui.ai_worker import AIWorker
from ui.pipeline_worker import PipelineWorker
from ui.diff_viewer import DiffViewerDialog
from ui.workspace_search_panel import WorkspaceSearchPanel
from ai.pipeline import PipelineRun, Stage
from ai.diff_engine import DiffEngine

# Assuming these exist from earlier steps (Stage 3 & 4)
try:
    from ui.activity_panel import ActivityPanel
except ImportError:
    ActivityPanel = QtWidgets.QTextEdit
try:
    from ui.pipeline_panel import PipelinePanel
except ImportError:
    PipelinePanel = QtWidgets.QTextEdit
try:
    from ui.task_queue_panel import TaskQueuePanel
except ImportError:
    TaskQueuePanel = QtWidgets.QTextEdit
try:
    from ui.conversation_history import ConversationHistoryPanel
except ImportError:
    ConversationHistoryPanel = QtWidgets.QTextEdit


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
        
        # Configuration/State
        self.config = {}
        self.provider_router = None
        self.diff_engine = DiffEngine()
        
        self.file_icon_provider = QtWidgets.QFileIconProvider()
        
        self._build_ui()
        self._setup_status_bar()

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
        self.project_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
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

        # RIGHT: AI Chat
        self.chat_panel = QtWidgets.QWidget(self)
        chat_layout = QtWidgets.QVBoxLayout(self.chat_panel)
        self.chat_output = QtWidgets.QTextEdit(self.chat_panel)
        self.chat_output.setReadOnly(True)
        self.chat_output.setPlaceholderText("AI chat will appear here.")
        
        # Stop Generation button
        self.stop_gen_button = QtWidgets.QPushButton("Stop Generation")
        self.stop_gen_button.hide()
        
        self.chat_input = QtWidgets.QLineEdit(self.chat_panel)
        self.chat_input.setPlaceholderText("Ask the assistant...")
        self.chat_input.returnPressed.connect(self._submit_chat)
        
        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.clicked.connect(self._submit_chat)
        
        input_layout = QtWidgets.QHBoxLayout()
        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(self.send_button)
        input_layout.addWidget(self.stop_gen_button)
        
        chat_layout.addWidget(self.chat_output)
        chat_layout.addLayout(input_layout)
        
        self.chat_dock = QtWidgets.QDockWidget("AI Chat", self)
        self.chat_dock.setWidget(self.chat_panel)
        self.chat_dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea)
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
        self.pipeline_panel = PipelinePanel() if callable(PipelinePanel) else PipelinePanel(self.agent_tabs)
        self.activity_panel = ActivityPanel() if callable(ActivityPanel) else ActivityPanel(self.agent_tabs)
        self.task_queue_panel = TaskQueuePanel() if callable(TaskQueuePanel) else TaskQueuePanel(self.agent_tabs)
        self.history_panel = ConversationHistoryPanel() if callable(ConversationHistoryPanel) else ConversationHistoryPanel(self.agent_tabs)
        
        self.agent_tabs.addTab(self.pipeline_panel, "Pipeline")
        self.agent_tabs.addTab(self.activity_panel, "Activity")
        self.agent_tabs.addTab(self.task_queue_panel, "Tasks")
        self.agent_tabs.addTab(self.history_panel, "History")
        
        self.agent_dock = QtWidgets.QDockWidget("Agent Panels", self)
        self.agent_dock.setWidget(self.agent_tabs)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.agent_dock)
        
        # Make the bottom docks split evenly
        self.splitDockWidget(self.workspace_dock, self.agent_dock, QtCore.Qt.Horizontal)

        # TOP: Toolbar
        self.toolbar = Toolbar(self)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.toolbar)
        self.toolbar_buttons = self.toolbar.buttons

        self.setDockNestingEnabled(True)

    def _setup_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")
        
        # Status indicators
        self.status_ollama = QtWidgets.QLabel("● Disconnected")
        self.status_ollama.setStyleSheet("color: red; font-weight: bold;")
        self.statusBar().addPermanentWidget(self.status_ollama)
        
        self.status_model = QtWidgets.QLabel("Model: Qwen")
        self.statusBar().addPermanentWidget(self.status_model)
        
        self.status_git = QtWidgets.QLabel("Git: main")
        self.statusBar().addPermanentWidget(self.status_git)
        
        self.status_cursor = QtWidgets.QLabel("Ln 1, Col 1")
        self.statusBar().addPermanentWidget(self.status_cursor)
        
        # Connect cursor changes
        self.central_editor.cursorPositionChanged.connect(self._update_cursor_status)

    def _update_cursor_status(self):
        cursor = self.central_editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.status_cursor.setText(f"Ln {line}, Col {col}")

    def update_model_status(self, model_name: str):
        self.status_model.setText(f"Model: {model_name}")

    # Directories and files that are never shown in the project tree
    _EXPLORER_IGNORE = {
        "build", "dist", "config_backups", "__pycache__", "node_modules",
        ".venv", "venv", ".mypy_cache", ".pytest_cache", ".tox",
        "crash_reports",
    }

    def _populate_project_explorer(self) -> None:
        self.project_explorer.clear()

        if hasattr(self, 'search_panel'):
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

    def _submit_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        
        self.chat_output.append(f'<b style="color:#007ACC;">You:</b> {text}')
        self.chat_output.append('<b style="color:#4EC9B0;">Agent:</b> ')
        self.chat_input.clear()
        
        if self.provider_router:
            model = self.toolbar.model_selector.currentText()
            # Simple mapping to internal model names if needed
            model_map = {
                "Ollama (Qwen)": "qwen2.5-coder:3b",
                "Claude": "claude-3-5-sonnet-20241022",
                "OpenAI": "gpt-4o",
                "Gemini": "gemini-1.5-pro"
            }
            mapped_model = model_map.get(model, model)
            
            self.stop_gen_button.show()
            self.chat_input.setEnabled(False)
            
            # Use current file as context if available
            system_prompt = "You are THTWAAT AI IDE Assistant."
            if self.current_path and os.path.exists(self.current_path):
                content = Path(self.current_path).read_text(encoding="utf-8")
                system_prompt += f"\n\nContext file '{Path(self.current_path).name}':\n```\n{content}\n```"

            self.ai_worker = AIWorker(self.provider_router, text, mapped_model, system_prompt, self)
            self.ai_worker.token_received.connect(self._on_ai_token)
            self.ai_worker.finished.connect(self._on_ai_finished)
            self.ai_worker.error_occurred.connect(self._on_ai_error)
            
            # Connect stop button
            self.stop_gen_button.clicked.connect(self.ai_worker.stop)
            
            self.ai_worker.start()
        else:
            self.chat_output.insertPlainText("Error: Provider Router not initialized.\n")

    def _on_ai_token(self, token: str):
        self.chat_output.insertPlainText(token)
        # Auto-scroll to bottom
        scrollbar = self.chat_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_ai_finished(self):
        self.chat_output.insertPlainText("\n")
        self._cleanup_ai_worker()

    def _on_ai_error(self, err: str):
        self.chat_output.insertPlainText(f"\n[Error: {err}]\n")
        self._cleanup_ai_worker()
        
    def _cleanup_ai_worker(self):
        self.stop_gen_button.hide()
        self.chat_input.setEnabled(True)
        self.chat_input.setFocus()
        try:
            self.stop_gen_button.clicked.disconnect(self.ai_worker.stop)
        except Exception:
            pass

    def new_file(self) -> None:
        if self.central_editor.document().isModified():
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 'Unsaved Changes',
                "Save changes before creating new file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_current_file()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
                
        self.current_path = None
        self.central_editor.set_text("")
        self.statusBar().showMessage("New file created")

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
        self.central_editor.document().setModified(False)

    def _on_search_result_selected(self, path: str, line: int):
        self.open_file(path)
        self.central_editor.goto_line(line)
        
    def _on_go_to_definition(self, word: str):
        if not hasattr(self, 'search_panel') or not self.search_panel.search_backend:
            return
        result = self.search_panel.search_backend.go_to_definition(word)
        if result:
            self.open_file(result.path)
            self.central_editor.goto_line(result.line)
            self.statusBar().showMessage(f"Jumped to definition of {word}")
        else:
            self.statusBar().showMessage(f"Definition not found for {word}")
            
    def _on_rename_symbol(self, old_name: str, new_name: str):
        if not hasattr(self, 'search_panel') or not self.search_panel.search_backend:
            return
            
        self.statusBar().showMessage(f"Renaming {old_name} to {new_name}...")
        diffs = self.search_panel.search_backend.rename_symbol(old_name, new_name, dry_run=True)
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

    def _on_inline_completion_requested(self, context_text: str):
        if not self.provider_router:
            return
            
        model = self.toolbar.model_selector.currentText()
        model_map = {
            "Ollama (Qwen)": "qwen2.5-coder:3b",
            "Claude": "claude-3-5-sonnet-20241022",
            "OpenAI": "gpt-4o",
            "Gemini": "gemini-1.5-pro"
        }
        mapped_model = model_map.get(model, model)
        
        system_prompt = "You are an inline autocomplete engine. Complete the code following the context. Provide ONLY the immediate next few words or line of code. No formatting or explanation."
        
        # Stop existing worker if running
        if hasattr(self, 'inline_worker') and self.inline_worker.isRunning():
            self.inline_worker.stop()
            self.inline_worker.wait()
            
        # We reuse AIWorker but handle the signal differently
        self.inline_worker = AIWorker(self.provider_router, context_text[-500:], mapped_model, system_prompt, self)
        
        # Accumulate tokens and show them
        self._inline_buffer = ""
        def handle_token(token):
            self._inline_buffer += token
            # Show first line
            self.central_editor.show_ghost_text(self._inline_buffer)
            
        self.inline_worker.token_received.connect(handle_token)
        self.inline_worker.start()

    def open_file(self, path: str) -> None:
        if os.path.exists(path):
            if self.central_editor.document().isModified():
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self, 'Unsaved Changes',
                    "Save changes before opening another file?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.save_current_file()
                elif reply == QMessageBox.StandardButton.Cancel:
                    return
                    
            self.current_path = path
            self.central_editor.open_file(path)
            self.statusBar().showMessage(f"Opened {path}")

    def run_code(self) -> None:
        if self.current_path and self.current_path.endswith(".py"):
            self.statusBar().showMessage(f"Running {self.current_path}")
            self.bottom_tabs.setCurrentIndex(0)
            
            cmd = f'python "{self.current_path}"'
            
            if hasattr(self.terminal_page, 'process') and self.terminal_page.process.state() == QtCore.QProcess.Running:
                # Add command to terminal text
                from PySide6 import QtGui
                cursor = self.terminal_page.textCursor()
                cursor.movePosition(QtGui.QTextCursor.End)
                self.terminal_page.setTextCursor(cursor)
                self.terminal_page.insertPlainText(cmd + "\n")
                
                # Update prompt position since we inserted text programmatically
                self.terminal_page.prompt_position = self.terminal_page.textCursor().position()
                
                self.terminal_page.expected_echo = cmd + "\n"
                self.terminal_page.process.write(cmd.encode('utf-8') + b'\r\n')
        else:
            self.statusBar().showMessage("No runnable Python file selected")

    def ai_edit(self) -> None:
        if not self.current_path:
            self.statusBar().showMessage("Open a file to edit first")
            return
            
        from PySide6.QtWidgets import QInputDialog
        prompt, ok = QInputDialog.getText(self, "AI Edit", "What would you like to change?")
        if not ok or not prompt:
            return

        self.chat_output.append(f"<b style='color:#007ACC;'>You:</b> Edit: {prompt}\n")
        self.chat_output.append("<b style='color:#4EC9B0;'>Agent:</b> Starting edit pipeline...\n")
        
        cursor = self.central_editor.textCursor()
        selected_text = cursor.selectedText()
        
        # QPlainTextEdit replaces newlines with U+2029 (Paragraph Separator) when getting selected text
        if selected_text:
            selected_text = selected_text.replace('\u2029', '\n')
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
        selected_text = cursor.selectedText()
        if selected_text:
            selected_text = selected_text.replace('\u2029', '\n')
            code_context = f"Selected code in {self.current_path}:\n```\n{selected_text}\n```"
            msg = "Explain the selected code."
        else:
            code_context = f"File content of {self.current_path}:\n```\n{self.central_editor.text()}\n```"
            msg = "Explain this file."

        self.chat_output.append(f'<b style="color:#007ACC;">You:</b> {msg}')
        self.chat_output.append('<b style="color:#4EC9B0;">Agent:</b> ')
        
        if self.provider_router:
            model = self.toolbar.model_selector.currentText()
            model_map = {
                "Ollama (Qwen)": "qwen2.5-coder:3b",
                "Claude": "claude-3-5-sonnet-20241022",
                "OpenAI": "gpt-4o",
                "Gemini": "gemini-1.5-pro"
            }
            mapped_model = model_map.get(model, model)
            
            self.stop_gen_button.show()
            self.chat_input.setEnabled(False)
            
            system_prompt = f"You are THTWAAT AI IDE Assistant.\n\nContext:\n{code_context}"

            self.ai_worker = AIWorker(self.provider_router, "Explain this code in detail.", mapped_model, system_prompt, self)
            self.ai_worker.token_received.connect(self._on_ai_token)
            self.ai_worker.finished.connect(self._on_ai_finished)
            self.ai_worker.error_occurred.connect(self._on_ai_error)
            
            self.stop_gen_button.clicked.connect(self.ai_worker.stop)
            self.ai_worker.start()
        else:
            self.chat_output.insertPlainText("Error: Provider Router not initialized.\n")

    def optimize(self) -> None:
        if not self.current_path:
            self.statusBar().showMessage("Open a file to optimize first")
            return
            
        # Show one-time experimental warning before running
        from PySide6.QtWidgets import QMessageBox
        warn = QMessageBox(self)
        warn.setWindowTitle("⚠️ Experimental Feature")
        warn.setIcon(QMessageBox.Icon.Warning)
        warn.setText(
            "<b>This feature is experimental.</b><br><br>"
            "The AI Optimize pipeline may produce <b>incorrect, trivial, or "
            "unrelated changes</b> depending on the model and file complexity.<br><br>"
            "<b>Always review every change carefully before accepting.</b><br><br>"
            "<i>Note: changes must be accepted or rejected together — "
            "individual file-level reject is not yet available.</i>"
        )
        warn.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        warn.setDefaultButton(QMessageBox.StandardButton.Ok)
        if warn.exec() != QMessageBox.StandardButton.Ok:
            return

        self.chat_output.append("<b style='color:#007ACC;'>You:</b> Optimize current file\n")
        self.chat_output.append("<b style='color:#4EC9B0;'>Agent:</b> Starting optimization pipeline...\n")
        
        # Prepare Pipeline
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

    def _on_pipeline_stage(self, stage_name: str, progress: int):
        self.statusBar().showMessage(f"Pipeline: {stage_name} ({progress}%)")
        self.chat_output.insertPlainText(f"-> {stage_name}...\n")
        
    def _on_pipeline_review_requested(self):
        # Show Diff Viewer
        dialog = DiffViewerDialog(self.diff_engine, self)
        if dialog.exec():
            # Accepted
            self.chat_output.insertPlainText("-> Changes accepted. Continuing...\n")
            if self.current_path:
                self.central_editor.open_file(self.current_path)  # reload
            self.pipeline_worker.resume(True)
        else:
            self.chat_output.insertPlainText("-> Changes rejected.\n")
            self.statusBar().showMessage("Optimization cancelled.")
            self.pipeline_worker.resume(False)

    def _on_pipeline_finished(self, success: bool, message: str):
        self.statusBar().showMessage(message)
        self.chat_output.insertPlainText(f"-> {message}\n")

    def git(self) -> None:
        self._submit_chat_with_message("Git", "Git workflow hooks are ready for the next integration step.")

    def _submit_chat_with_message(self, title: str, message: str) -> None:
        self.chat_output.append(f"[{title}] {message}\n")

    def closeEvent(self, event: QtCore.QEvent) -> None:
        event.accept()
