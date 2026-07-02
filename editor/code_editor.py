import os
from pathlib import Path

from PySide6 import QtGui, QtWidgets
from PySide6.QtWidgets import QWidget

try:
    from PySide6.Qsci import QsciScintilla, QsciLexerPython
except ImportError:  # pragma: no cover
    QsciScintilla = None
    QsciLexerPython = None


class CodeEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CodeEditor")
        self._editor = self._create_editor()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._editor)

    def _create_editor(self):
        if QsciScintilla is not None and QsciLexerPython is not None:
            editor = QsciScintilla(self)
            editor.setUtf8(True)
            editor.setLexer(QsciLexerPython(editor))
            editor.setMarginType(0, QsciScintilla.NumberMargin)
            editor.setMarginLineNumbers(0, True)
            editor.setMarginsForegroundColor(QtGui.QColor("#9ca3af"))
            editor.setMarginsBackgroundColor(QtGui.QColor("#111827"))
            editor.setCaretLineVisible(True)
            editor.setCaretLineBackgroundColor(QtGui.QColor("#1f2937"))
            editor.setAutoIndent(True)
            editor.setIndentationsUseTabs(False)
            editor.setTabWidth(4)
            editor.setBraceMatching(QsciScintilla.StrictBraceMatch)
            editor.setEdgeMode(QsciScintilla.EdgeLine)
            editor.setEdgeColumn(100)
            editor.setEdgeColor(QtGui.QColor("#374151"))
            editor.setFolding(QsciScintilla.BoxedTreeFoldStyle)
            editor.setWrapMode(QsciScintilla.WrapWord)
            return editor

        editor = QtWidgets.QPlainTextEdit(self)
        editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        editor.setTabStopDistance(4 * editor.fontMetrics().horizontalAdvance(" "))
        return editor

    def set_text(self, text: str) -> None:
        if hasattr(self._editor, "setPlainText"):
            self._editor.setPlainText(text)
        else:
            self._editor.setText(text)

    def text(self) -> str:
        if hasattr(self._editor, "toPlainText"):
            return self._editor.toPlainText()
        return self._editor.text()

    def open_file(self, path: str) -> None:
        if os.path.exists(path):
            self.set_text(Path(path).read_text(encoding="utf-8", errors="ignore"))

    def save_file(self, path: str) -> None:
        Path(path).write_text(self.text(), encoding="utf-8")
