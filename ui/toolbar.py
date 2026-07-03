from PySide6 import QtWidgets


class Toolbar(QtWidgets.QToolBar):
    def __init__(self, parent):
        super().__init__(parent)
        self.setMovable(False)
        self.buttons: list[QtWidgets.QPushButton] = []
        
        # We need a reference to main window to trigger model changes
        self.main_window = parent

        self._add_button("New File", parent.new_file)
        self._add_button("Open Folder", parent.open_folder)
        self._add_button("Save", parent.save_current_file)
        self._add_button("Run", parent.run_code)
        self.addSeparator()
        self._add_button("AI Edit", parent.ai_edit)
        self._add_button("Explain", parent.explain)
        self._add_button("Optimize", parent.optimize)
        
        self.addSeparator()
        
        # Model Selector
        self.model_selector = QtWidgets.QComboBox()
        self.model_selector.addItems([
            "Ollama (Qwen)",
            "Claude",
            "OpenAI",
            "Gemini"
        ])
        self.model_selector.currentTextChanged.connect(self._on_model_changed)
        self.addWidget(self.model_selector)
        
        self.addSeparator()
        self._add_button("Git", parent.git)

    def _add_button(self, text: str, command) -> None:
        button = QtWidgets.QPushButton(text)
        button.clicked.connect(command)
        self.addWidget(button)
        self.buttons.append(button)

    def _on_model_changed(self, text: str):
        if hasattr(self.main_window, "update_model_status"):
            self.main_window.update_model_status(text)
