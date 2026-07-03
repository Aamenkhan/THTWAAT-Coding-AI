from PySide6 import QtWidgets, QtGui, QtCore

class DiffViewerDialog(QtWidgets.QDialog):
    def __init__(self, diff_engine, parent=None):
        super().__init__(parent)
        self.diff_engine = diff_engine
        self.setWindowTitle("Review Optimization (Diff)")
        self.resize(900, 650)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        self.diff_editor = QtWidgets.QTextEdit(self)
        self.diff_editor.setReadOnly(True)
        self.diff_editor.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        font = QtGui.QFont("Consolas", 10)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.diff_editor.setFont(font)
        
        layout.addWidget(self.diff_editor)
        
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self)
        button_box.button(QtWidgets.QDialogButtonBox.Ok).setText("Accept Changes")
        button_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("Reject")
        button_box.accepted.connect(self._accept_all)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
        self._refresh()

    def _refresh(self):
        edits = list(self.diff_engine.pending_edits())
        if not edits:
            self.diff_editor.setHtml("<h3>No pending changes.</h3>")
            return
        
        html = "<pre style='margin:0;'>"
        for edit in edits:
            html += f"<strong style='color:#CCCCCC;'>File: {edit.path}</strong><br>"
            for line in edit.diff.splitlines():
                line_safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                if line.startswith("+"):
                    html += f"<span style='color:#A6E22E; background-color:#1E3A24;'>{line_safe}</span><br>"
                elif line.startswith("-"):
                    html += f"<span style='color:#F92672; background-color:#4A1C1C;'>{line_safe}</span><br>"
                elif line.startswith("@@"):
                    html += f"<span style='color:#66D9EF;'>{line_safe}</span><br>"
                else:
                    html += f"<span style='color:#CCCCCC;'>{line_safe}</span><br>"
            html += "<br><hr><br>"
        html += "</pre>"
        self.diff_editor.setHtml(html)

    def _accept_all(self):
        self.diff_engine.accept_all()
        self.accept()
