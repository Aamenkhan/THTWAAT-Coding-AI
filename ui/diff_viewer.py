from PySide6 import QtWidgets, QtGui, QtCore


class DiffViewerDialog(QtWidgets.QDialog):
    """
    Shows all pending diffs from DiffEngine.
    Left panel: file list with per-file Accept / Reject buttons.
    Right panel: unified diff for the selected file.
    Bottom: Accept All / Reject All shortcuts.
    """

    def __init__(self, diff_engine, parent=None):
        super().__init__(parent)
        self.diff_engine = diff_engine
        self.setWindowTitle("Review Changes")
        self.resize(1100, 700)

        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)

        # ── Left: file list ──────────────────────────────────────────
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        left_label = QtWidgets.QLabel("Changed files")
        left_label.setStyleSheet("font-weight: bold; color: #CCCCCC;")
        left_layout.addWidget(left_label)

        self.file_list = QtWidgets.QListWidget()
        self.file_list.setObjectName("DiffFileList")
        self.file_list.setMinimumWidth(220)
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        left_layout.addWidget(self.file_list)

        # Per-file buttons
        per_file_row = QtWidgets.QHBoxLayout()
        self.btn_accept_file = QtWidgets.QPushButton("✅ Accept File")
        self.btn_reject_file = QtWidgets.QPushButton("❌ Reject File")
        self.btn_accept_file.setObjectName("AcceptFileBtn")
        self.btn_reject_file.setObjectName("RejectFileBtn")
        self.btn_accept_file.clicked.connect(self._accept_selected)
        self.btn_reject_file.clicked.connect(self._reject_selected)
        per_file_row.addWidget(self.btn_accept_file)
        per_file_row.addWidget(self.btn_reject_file)
        left_layout.addLayout(per_file_row)

        splitter.addWidget(left_widget)

        # ── Right: diff viewer ───────────────────────────────────────
        self.diff_editor = QtWidgets.QTextEdit()
        self.diff_editor.setObjectName("DiffEditor")
        self.diff_editor.setReadOnly(True)
        self.diff_editor.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        font = QtGui.QFont("Consolas", 10)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.diff_editor.setFont(font)
        splitter.addWidget(self.diff_editor)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        root_layout.addWidget(splitter, stretch=1)

        # ── Bottom: bulk actions + status label ──────────────────────
        bottom_row = QtWidgets.QHBoxLayout()

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #888888; font-style: italic;")
        bottom_row.addWidget(self.status_label, stretch=1)

        self.btn_accept_all = QtWidgets.QPushButton("✅ Accept All")
        self.btn_reject_all = QtWidgets.QPushButton("❌ Reject All")
        self.btn_done = QtWidgets.QPushButton("Done")
        self.btn_accept_all.setObjectName("AcceptAllBtn")
        self.btn_reject_all.setObjectName("RejectAllBtn")
        self.btn_done.setObjectName("DoneBtn")
        self.btn_accept_all.clicked.connect(self._accept_all)
        self.btn_reject_all.clicked.connect(self._reject_all)
        self.btn_done.clicked.connect(self.accept)

        bottom_row.addWidget(self.btn_accept_all)
        bottom_row.addWidget(self.btn_reject_all)
        bottom_row.addWidget(self.btn_done)
        root_layout.addLayout(bottom_row)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Reload file list from DiffEngine pending edits."""
        self.file_list.clear()

        edits = list(self.diff_engine.pending_edits())
        if not edits:
            self.diff_editor.setHtml("<h3 style='color:#CCCCCC;'>No pending changes.</h3>")
            self.btn_accept_file.setEnabled(False)
            self.btn_reject_file.setEnabled(False)
            self.btn_accept_all.setEnabled(False)
            self.btn_reject_all.setEnabled(False)
            self._update_status()
            return

        for edit in edits:
            item = QtWidgets.QListWidgetItem(self._short_name(edit.path))
            item.setData(QtCore.Qt.UserRole, edit.path)
            item.setToolTip(edit.path)
            self.file_list.addItem(item)

        self.file_list.setCurrentRow(0)
        self._update_status()

    def _on_file_selected(self, row: int) -> None:
        if row < 0:
            self.diff_editor.clear()
            return
        item = self.file_list.item(row)
        if not item:
            return
        path = item.data(QtCore.Qt.UserRole)
        edit = self.diff_engine.preview(path)
        if edit is None:
            self.diff_editor.setHtml("<i style='color:#888;'>Already processed.</i>")
            return
        self.diff_editor.setHtml(self._render_diff(edit))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _accept_selected(self) -> None:
        item = self.file_list.currentItem()
        if not item:
            return
        path = item.data(QtCore.Qt.UserRole)
        self.diff_engine.accept(path)
        item.setText("✅ " + self._short_name(path))
        item.setForeground(QtGui.QColor("#A6E22E"))
        self.btn_accept_file.setEnabled(False)
        self.btn_reject_file.setEnabled(False)
        self._update_status()

    def _reject_selected(self) -> None:
        item = self.file_list.currentItem()
        if not item:
            return
        path = item.data(QtCore.Qt.UserRole)
        self.diff_engine.reject(path)
        item.setText("❌ " + self._short_name(path))
        item.setForeground(QtGui.QColor("#F92672"))
        self.btn_accept_file.setEnabled(False)
        self.btn_reject_file.setEnabled(False)
        self._update_status()

    def _accept_all(self) -> None:
        self.diff_engine.accept_all()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            path = item.data(QtCore.Qt.UserRole)
            item.setText("✅ " + self._short_name(path))
            item.setForeground(QtGui.QColor("#A6E22E"))
        self.btn_accept_file.setEnabled(False)
        self.btn_reject_file.setEnabled(False)
        self.btn_accept_all.setEnabled(False)
        self.btn_reject_all.setEnabled(False)
        self._update_status()

    def _reject_all(self) -> None:
        self.diff_engine.reject_all()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            path = item.data(QtCore.Qt.UserRole)
            item.setText("❌ " + self._short_name(path))
            item.setForeground(QtGui.QColor("#F92672"))
        self.btn_accept_file.setEnabled(False)
        self.btn_reject_file.setEnabled(False)
        self.btn_accept_all.setEnabled(False)
        self.btn_reject_all.setEnabled(False)
        self._update_status()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        pending = self.diff_engine.pending_edits()
        total = self.file_list.count()
        processed = total - len(pending)
        self.status_label.setText(f"{processed}/{total} files processed")

    @staticmethod
    def _short_name(path: str) -> str:
        from pathlib import Path
        return Path(path).name

    @staticmethod
    def _render_diff(edit) -> str:
        """Return syntax-coloured HTML for a PendingEdit's unified diff."""
        html = "<pre style='margin:0; font-family:Consolas,monospace; font-size:10pt;'>"
        html += f"<strong style='color:#CCCCCC;'>File: {edit.path}</strong><br>"
        if not edit.diff:
            html += "<span style='color:#888;'>(no textual diff — binary or unchanged)</span>"
        else:
            for line in edit.diff.splitlines():
                line_safe = (
                    line.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                )
                if line.startswith("+") and not line.startswith("+++"):
                    html += f"<span style='color:#A6E22E; background:#1E3A24;'>{line_safe}</span><br>"
                elif line.startswith("-") and not line.startswith("---"):
                    html += f"<span style='color:#F92672; background:#4A1C1C;'>{line_safe}</span><br>"
                elif line.startswith("@@"):
                    html += f"<span style='color:#66D9EF;'>{line_safe}</span><br>"
                else:
                    html += f"<span style='color:#CCCCCC;'>{line_safe}</span><br>"
        html += "</pre>"
        return html
