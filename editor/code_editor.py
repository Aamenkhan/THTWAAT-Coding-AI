import os
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QRect, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QTextFormat, QTextCursor, QFontMetrics
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextEdit, QMenu, QInputDialog, QLabel

from editor.syntax_highlighter import PythonSyntaxHighlighter


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    # Signals for navigation
    go_to_definition_requested = Signal(str)
    rename_symbol_requested = Signal(str, str)
    inline_completion_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CodeEditor")
        
        self.line_number_area = LineNumberArea(self)
        
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        
        # Set font
        font = QtGui.QFont("Consolas", 11)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.setFont(font)
        
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        
        # Syntax highlighter
        self.highlighter = PythonSyntaxHighlighter(self.document())

        # Inline AI Suggestions (Ghost Text)
        self._ghost_label = QLabel(self)
        self._ghost_label.setStyleSheet("color: #7A7A7A; background-color: transparent;")
        
        ghost_font = QtGui.QFont(font)
        ghost_font.setItalic(True)
        self._ghost_label.setFont(ghost_font)
        
        self._ghost_label.hide()
        self._ghost_text = ""
        
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(750)  # 750ms debounce
        self._debounce_timer.timeout.connect(self._request_inline_completion)
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self):
        self._hide_ghost_text()
        self._debounce_timer.start()

    def _request_inline_completion(self):
        cursor = self.textCursor()
        # Only request if at end of a line or end of file
        if not cursor.atBlockEnd():
            return
            
        # Get last 1000 chars as context
        text = self.toPlainText()
        pos = cursor.position()
        context = text[max(0, pos - 1000):pos]
        
        if context.strip():
            self.inline_completion_requested.emit(context)

    def show_ghost_text(self, suggestion: str):
        if not suggestion or not self.hasFocus():
            return
            
        # Only take first line of suggestion for inline to keep it clean
        first_line = suggestion.split('\n')[0]
        if not first_line:
            return
            
        self._ghost_text = first_line
        self._ghost_label.setText(self._ghost_text)
        
        # Position label at cursor
        cursor_rect = self.cursorRect(self.textCursor())
        fm = self.fontMetrics()
        
        self._ghost_label.move(
            cursor_rect.right() + fm.horizontalAdvance(" "),
            cursor_rect.top()
        )
        self._ghost_label.resize(
            fm.horizontalAdvance(self._ghost_text) + 10,
            cursor_rect.height()
        )
        self._ghost_label.show()

    def _hide_ghost_text(self):
        self._ghost_text = ""
        self._ghost_label.hide()

    def line_number_area_width(self):
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val /= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#2A2D2E")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#1E1E1E"))
        
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#858585"))
                painter.drawText(0, top, self.line_number_area.width() - 5, self.fontMetrics().height(),
                                 Qt.AlignRight, number)
            
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def keyPressEvent(self, event):
        if self._ghost_label.isVisible():
            if event.key() == Qt.Key_Tab:
                # Accept ghost text
                cursor = self.textCursor()
                cursor.insertText(self._ghost_text)
                self._hide_ghost_text()
                return
            elif event.key() != Qt.Key_Shift and event.key() != Qt.Key_Control:
                self._hide_ghost_text()
                
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Auto-indent
            cursor = self.textCursor()
            line_text = cursor.block().text()
            indent = ""
            for char in line_text:
                if char in (' ', '\t'):
                    indent += char
                else:
                    break
            if line_text.strip().endswith(':'):
                indent += "    "
            super().keyPressEvent(event)
            self.insertPlainText(indent)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.modifiers() == Qt.ControlModifier:
            cursor = self.cursorForPosition(event.pos())
            cursor.select(QTextCursor.WordUnderCursor)
            word = cursor.selectedText()
            if word:
                self.go_to_definition_requested.emit(word)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        rename_action = menu.addAction("Rename Symbol")
        
        action = menu.exec(event.globalPos())
        if action == rename_action:
            cursor = self.cursorForPosition(event.pos())
            cursor.select(QTextCursor.WordUnderCursor)
            old_name = cursor.selectedText()
            if old_name:
                new_name, ok = QInputDialog.getText(self, "Rename Symbol", f"Rename '{old_name}' to:")
                if ok and new_name and new_name != old_name:
                    self.rename_symbol_requested.emit(old_name, new_name)

    def set_text(self, text: str) -> None:
        self.setPlainText(text)

    def text(self) -> str:
        return self.toPlainText()

    def open_file(self, path: str) -> None:
        if os.path.exists(path):
            self.set_text(Path(path).read_text(encoding="utf-8", errors="ignore"))

    def goto_line(self, line: int) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.Start)
        cursor.movePosition(QtGui.QTextCursor.Down, QtGui.QTextCursor.MoveAnchor, line - 1)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.highlight_current_line()

    def save_file(self, path: str) -> None:
        Path(path).write_text(self.text(), encoding="utf-8")
