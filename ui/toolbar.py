"""
ui/toolbar.py — Application Toolbar
Phase 3: Grouped model selector storing actual model IDs in Qt.UserRole data.
         Selecting a model calls main_window.switch_model(provider, model_id).
         Settings button stub (Phase 6 will wire the dialog).
"""

from PySide6 import QtCore, QtGui, QtWidgets

# ── Model registry ────────────────────────────────────────────────────────────
# (provider_key, [(display_name, model_id), ...])
_MODEL_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("ollama", [
        ("qwen2.5-coder:3b", "qwen2.5-coder:3b"),
        ("qwen2.5-coder:7b", "qwen2.5-coder:7b"),
        ("deepseek-coder",   "deepseek-coder"),
    ]),
    ("gemini", [
        ("gemini-flash-latest", "gemini-flash-latest"),
        ("gemini-2.5-flash",    "gemini-2.5-flash"),
        ("gemini-2.5-pro",      "gemini-2.5-pro"),
    ]),
]

_FUTURE_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("future", [
        ("GPT-4o",        "gpt-4o"),
        ("Claude Sonnet", "claude-3-5-sonnet-20241022"),
    ]),
]

_ROLE_MODEL_ID = QtCore.Qt.UserRole       # stores the actual model ID string
_ROLE_PROVIDER = QtCore.Qt.UserRole + 1   # stores the provider key string


class Toolbar(QtWidgets.QToolBar):
    def __init__(self, parent):
        super().__init__(parent)
        self.setMovable(False)
        self.buttons: list[QtWidgets.QPushButton] = []
        self.main_window = parent

        # ── Standard action buttons ──────────────────────────────────────────
        self._add_button("New File",    parent.new_file)
        self._add_button("Open Folder", parent.open_folder)
        self._add_button("Save",        parent.save_current_file)
        self._add_button("Run",         parent.run_code)
        self.addSeparator()
        self._add_button("AI Edit",  parent.ai_edit)
        self._add_button("Explain",  parent.explain)
        self._add_button("Optimize", parent.optimize)
        self.addSeparator()

        # ── Grouped model selector ───────────────────────────────────────────
        self.model_selector = QtWidgets.QComboBox()
        self.model_selector.setMinimumWidth(180)
        self.model_selector.setToolTip("Select AI provider and model")
        self._populate_model_combo()
        # Use index change so we can read UserRole data (not display text)
        self.model_selector.currentIndexChanged.connect(self._on_model_index_changed)
        self.addWidget(self.model_selector)

        self.addSeparator()
        self._add_button("Git", parent.git)
        self.addSeparator()
        self._add_button("⚙ Settings", parent.open_settings)

    # ── Combo population ─────────────────────────────────────────────────────

    def _populate_model_combo(self) -> None:
        """Build a QStandardItemModel with grouped, labelled sections."""
        std_model = QtGui.QStandardItemModel()

        for provider, entries in _MODEL_GROUPS:
            self._add_separator_row(std_model, provider.title())
            for display, model_id in entries:
                item = QtGui.QStandardItem(f"  {display}")
                item.setData(model_id, _ROLE_MODEL_ID)
                item.setData(provider, _ROLE_PROVIDER)
                std_model.appendRow(item)

        # Future providers — visible but not selectable
        self._add_separator_row(std_model, "Future")
        for _, entries in _FUTURE_GROUPS:
            for display, model_id in entries:
                item = QtGui.QStandardItem(f"  {display}  (coming soon)")
                item.setFlags(QtCore.Qt.NoItemFlags)
                item.setData(QtGui.QColor("#555555"), QtCore.Qt.ForegroundRole)
                std_model.appendRow(item)

        self.model_selector.setModel(std_model)
        # Default selection: first real item (index 1, after "Ollama" separator)
        self.model_selector.setCurrentIndex(1)

    def _add_separator_row(self, model: QtGui.QStandardItemModel, label: str) -> None:
        """Insert a non-selectable group header row."""
        item = QtGui.QStandardItem(f"── {label} ──")
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setData(QtGui.QColor("#8b949e"), QtCore.Qt.ForegroundRole)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        model.appendRow(item)

    # ── Selection handling ───────────────────────────────────────────────────

    def _on_model_index_changed(self, index: int) -> None:
        """Propagate model selection to MainWindow.switch_model()."""
        model_id = self.model_selector.itemData(index, _ROLE_MODEL_ID)
        provider  = self.model_selector.itemData(index, _ROLE_PROVIDER)
        if model_id and provider and hasattr(self.main_window, "switch_model"):
            self.main_window.switch_model(provider, model_id)

    def set_model(self, model_id: str) -> None:
        """Select the combo item whose _ROLE_MODEL_ID data matches model_id."""
        std_model = self.model_selector.model()
        for i in range(std_model.rowCount()):
            item = std_model.item(i)
            if item and item.data(_ROLE_MODEL_ID) == model_id:
                # Block signal to avoid triggering switch_model during init
                self.model_selector.blockSignals(True)
                self.model_selector.setCurrentIndex(i)
                self.model_selector.blockSignals(False)
                return

    def get_model_id(self) -> str:
        """Return the active model ID (UserRole data). Falls back to display text."""
        idx = self.model_selector.currentIndex()
        return self.model_selector.itemData(idx, _ROLE_MODEL_ID) \
            or self.model_selector.currentText().strip()

    def get_provider(self) -> str:
        """Return the active provider key (e.g. 'ollama', 'gemini')."""
        idx = self.model_selector.currentIndex()
        return self.model_selector.itemData(idx, _ROLE_PROVIDER) or "ollama"

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _add_button(self, text: str, command) -> None:
        button = QtWidgets.QPushButton(text)
        button.clicked.connect(command)
        self.addWidget(button)
        self.buttons.append(button)
