import os
from PySide6 import QtCore, QtGui, QtWidgets

class TerminalWidget(QtWidgets.QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QtCore.QProcess(self)
        self.process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_ready_read)
        
        self.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        
        # Start cmd.exe on Windows
        self.process.start("cmd.exe", [])
        
        self.prompt_position = self.textCursor().position()
        self.history = []
        self.history_idx = 0
        
        # Apply dark styling like a terminal
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                font-family: Consolas, Courier New, monospace;
            }
        """)

    def on_ready_read(self):
        output = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        output = output.replace('\r\n', '\n')
        
        # Handle echo suppression
        if hasattr(self, 'expected_echo') and self.expected_echo:
            if output.startswith(self.expected_echo):
                output = output[len(self.expected_echo):]
                self.expected_echo = None
            elif self.expected_echo.startswith(output):
                self.expected_echo = self.expected_echo[len(output):]
                output = ""
            else:
                self.expected_echo = None
                
        if not output:
            return
            
        # Move cursor to end to append output
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.setTextCursor(cursor)
        
        # Insert output
        cursor.insertText(output)
        
        # Update the prompt position so user can only type after this
        self.prompt_position = self.textCursor().position()
        
        # Ensure scroll to bottom
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        cursor = self.textCursor()
        
        # Handle Enter/Return
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            cursor.movePosition(QtGui.QTextCursor.End)
            # Extract the command user typed after the last prompt
            cursor.setPosition(self.prompt_position, QtGui.QTextCursor.KeepAnchor)
            command = cursor.selectedText()
            
            # Clear selection and move to end
            cursor.clearSelection()
            cursor.movePosition(QtGui.QTextCursor.End)
            self.setTextCursor(cursor)
            
            # Add newline locally
            self.insertPlainText("\n")
            
            # Send command to process
            if self.process.state() == QtCore.QProcess.Running:
                self.expected_echo = command + "\n"
                self.process.write(command.encode('utf-8') + b'\r\n')
            
            # Update prompt position to the start of the new line
            self.prompt_position = self.textCursor().position()
            
            # Add to history
            if command.strip():
                self.history.append(command)
            self.history_idx = len(self.history)
            
            return # Do not process the enter key normally
            
        # Handle Backspace
        elif event.key() == QtCore.Qt.Key_Backspace:
            if cursor.position() <= self.prompt_position:
                return # Don't allow backspacing into output
                
        # Handle Left Arrow
        elif event.key() == QtCore.Qt.Key_Left:
            if cursor.position() <= self.prompt_position:
                return
                
        # Handle Up Arrow (History)
        elif event.key() == QtCore.Qt.Key_Up:
            if self.history and self.history_idx > 0:
                self.history_idx -= 1
                self.replace_current_input(self.history[self.history_idx])
            return
            
        # Handle Down Arrow (History)
        elif event.key() == QtCore.Qt.Key_Down:
            if self.history and self.history_idx < len(self.history) - 1:
                self.history_idx += 1
                self.replace_current_input(self.history[self.history_idx])
            elif self.history_idx == len(self.history) - 1:
                self.history_idx += 1
                self.replace_current_input("")
            return

        # Ensure we are typing at or after prompt position
        if cursor.position() < self.prompt_position:
            cursor.movePosition(QtGui.QTextCursor.End)
            self.setTextCursor(cursor)

        super().keyPressEvent(event)

    def replace_current_input(self, text):
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.setPosition(self.prompt_position, QtGui.QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(text)
