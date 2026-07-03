"""
ui/theme.py — VS Code style Dark Theme
"""

VS_CODE_DARK_THEME = """
QWidget {
    background-color: #1E1E1E;
    color: #CCCCCC;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow::separator {
    background: #2D2D2D;
    width: 2px;
    height: 2px;
}

/* Toolbars */
QToolBar {
    background-color: #333333;
    border: none;
    spacing: 5px;
    padding: 3px;
}

QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px;
    color: #CCCCCC;
}

QToolButton:hover {
    background-color: #444444;
}

QToolButton:pressed {
    background-color: #2D2D2D;
}

/* Dock Widgets */
QDockWidget {
    titlebar-close-icon: url();
    titlebar-normal-icon: url();
    background: #252526;
    color: #CCCCCC;
    font-weight: bold;
}

QDockWidget::title {
    background: #2D2D2D;
    padding: 4px 8px;
}

/* Tree Widget (Project Explorer) */
QTreeWidget {
    background-color: #252526;
    border: none;
    color: #CCCCCC;
    outline: none;
}

QTreeWidget::item:hover {
    background-color: #2A2D2E;
}

QTreeWidget::item:selected {
    background-color: #37373D;
    color: #FFFFFF;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #2D2D2D;
    background: #1E1E1E;
}

QTabBar::tab {
    background: #2D2D2D;
    color: #969696;
    padding: 6px 12px;
    border: none;
    border-right: 1px solid #1E1E1E;
}

QTabBar::tab:selected {
    background: #1E1E1E;
    color: #FFFFFF;
    border-top: 1px solid #007ACC;
}

QTabBar::tab:hover:!selected {
    background: #333333;
}

/* Text Editors & Line Edits */
QTextEdit, QPlainTextEdit, QLineEdit {
    background-color: #1E1E1E;
    color: #D4D4D4;
    border: 1px solid #3C3C3C;
    selection-background-color: #264F78;
}

QLineEdit {
    padding: 4px;
    border-radius: 2px;
}

QLineEdit:focus {
    border: 1px solid #007ACC;
}

/* Status Bar */
QStatusBar {
    background-color: #007ACC;
    color: #FFFFFF;
}

QStatusBar::item {
    border: none;
}

QStatusBar QLabel {
    color: #FFFFFF;
    padding: 0 5px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #1E1E1E;
    width: 14px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #424242;
    min-height: 20px;
    border: 3px solid #1E1E1E;
    border-radius: 7px;
}

QScrollBar::handle:vertical:hover {
    background: #4F4F4F;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #1E1E1E;
    height: 14px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #424242;
    min-width: 20px;
    border: 3px solid #1E1E1E;
    border-radius: 7px;
}

QScrollBar::handle:horizontal:hover {
    background: #4F4F4F;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ComboBox */
QComboBox {
    background-color: #3C3C3C;
    color: #CCCCCC;
    border: 1px solid #3C3C3C;
    border-radius: 2px;
    padding: 2px 8px;
}

QComboBox:hover {
    background-color: #4C4C4C;
}

QComboBox::drop-down {
    border: none;
}

QComboBox QAbstractItemView {
    background-color: #252526;
    border: 1px solid #454545;
    selection-background-color: #094771;
}

/* Buttons */
QPushButton {
    background-color: #0E639C;
    color: #FFFFFF;
    border: none;
    border-radius: 2px;
    padding: 6px 12px;
}

QPushButton:hover {
    background-color: #1177BB;
}

QPushButton:pressed {
    background-color: #094771;
}

QPushButton:disabled {
    background-color: #3C3C3C;
    color: #888888;
}
"""
