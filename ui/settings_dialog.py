"""
ui/settings_dialog.py — Settings Dialog
Phase 6: Full QDialog with left category list + right stacked pages.
Sections: General, Providers, Editor, Shortcuts, Model, Generation.
Saves to config.json on Apply. Does NOT restart the application.
"""

from __future__ import annotations

from typing import Any, Dict

from PySide6 import QtCore, QtGui, QtWidgets


class SettingsDialog(QtWidgets.QDialog):
    """
    Settings dialog with sidebar navigation + stacked content pages.

    Categories:
        General     — Theme (Dark / Light)
        Providers   — Gemini API Key (masked), Ollama URL
        Editor      — Font size, Tab width, Word wrap
        Shortcuts   — Read-only keyboard reference table
        Model       — Default model dropdown
        Generation  — Temperature slider, Max Tokens spinbox

    On Apply: saves to config.json via ConfigManager and calls
              main_window.set_config() to apply changes without restart.
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        # Work on a shallow copy so Cancel leaves original intact
        self.config: Dict[str, Any] = dict(main_window.config)

        self.setWindowTitle("Settings — THTWAAT Coding AI")
        self.setMinimumSize(660, 480)
        self.resize(700, 520)
        self.setModal(True)

        self._build()
        self._load_values()

    # ── Top-level layout ──────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        hdr = QtWidgets.QFrame()
        hdr.setStyleSheet("background:#161b22; border-bottom:1px solid #30363d;")
        hdr.setFixedHeight(46)
        hdr_lay = QtWidgets.QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(18, 0, 18, 0)
        title_lbl = QtWidgets.QLabel("⚙  Settings")
        title_lbl.setStyleSheet(
            "color:#e6edf3; font-size:14px; font-weight:bold; background:transparent;"
        )
        hdr_lay.addWidget(title_lbl)
        root.addWidget(hdr)

        # Body: left list + right stacked pages
        body_lay = QtWidgets.QHBoxLayout()
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # Left category list
        self._cat_list = QtWidgets.QListWidget()
        self._cat_list.setFixedWidth(154)
        self._cat_list.setStyleSheet("""
            QListWidget {
                background:#161b22; border:none;
                border-right:1px solid #30363d;
                color:#8b949e; font-size:12px; padding:4px 0;
            }
            QListWidget::item { padding:8px 16px; }
            QListWidget::item:selected {
                background:#21262d; color:#e6edf3;
                border-left:2px solid #58a6ff;
            }
            QListWidget::item:hover { background:#1c2128; color:#e6edf3; }
        """)
        for cat in ("General", "Providers", "Editor", "Shortcuts", "Model", "Generation"):
            self._cat_list.addItem(cat)
        self._cat_list.setCurrentRow(0)
        self._cat_list.currentRowChanged.connect(self._on_cat_changed)
        body_lay.addWidget(self._cat_list)

        # Right stacked widget
        self._stack = QtWidgets.QStackedWidget()
        self._stack.setStyleSheet("background:#0d1117;")
        for builder in (
            self._page_general,
            self._page_providers,
            self._page_editor,
            self._page_shortcuts,
            self._page_model,
            self._page_generation,
        ):
            self._stack.addWidget(builder())
        body_lay.addWidget(self._stack, 1)

        body_widget = QtWidgets.QWidget()
        body_widget.setLayout(body_lay)
        root.addWidget(body_widget, 1)

        # Bottom button bar
        btn_bar = QtWidgets.QFrame()
        btn_bar.setStyleSheet("background:#161b22; border-top:1px solid #30363d;")
        btn_lay = QtWidgets.QHBoxLayout(btn_bar)
        btn_lay.setContentsMargins(16, 8, 16, 8)
        btn_lay.setSpacing(8)
        btn_lay.addStretch()

        self._apply_btn = QtWidgets.QPushButton("Apply")
        self._apply_btn.setStyleSheet(self._btn_css("#0e639c", "#1177bb"))
        self._apply_btn.clicked.connect(self._apply)

        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.setStyleSheet(self._btn_css("#3fb950", "#2ea043"))
        ok_btn.clicked.connect(self._ok)

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setStyleSheet(self._btn_css("#21262d", "#2d333b"))
        cancel_btn.clicked.connect(self.reject)

        btn_lay.addWidget(self._apply_btn)
        btn_lay.addWidget(ok_btn)
        btn_lay.addWidget(cancel_btn)
        root.addWidget(btn_bar)

    # ── Page builders ─────────────────────────────────────────────────────────

    def _make_page(self, title: str) -> tuple[QtWidgets.QWidget, QtWidgets.QFormLayout]:
        """Return (page_widget, form_layout) with a titled header."""
        page = QtWidgets.QWidget()
        vlay = QtWidgets.QVBoxLayout(page)
        vlay.setContentsMargins(24, 20, 24, 20)
        vlay.setSpacing(10)

        lbl = QtWidgets.QLabel(title)
        lbl.setStyleSheet("color:#e6edf3; font-size:14px; font-weight:bold;")
        vlay.addWidget(lbl)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color:#30363d;")
        vlay.addWidget(sep)

        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        vlay.addLayout(form)
        vlay.addStretch()
        return page, form

    def _page_general(self) -> QtWidgets.QWidget:
        page, form = self._make_page("General")

        theme_lbl = QtWidgets.QLabel("Theme:")
        theme_lbl.setStyleSheet(self._lbl_css())
        self._theme_combo = QtWidgets.QComboBox()
        self._theme_combo.addItems(["Dark (VS Code)", "Light"])
        self._theme_combo.setStyleSheet(self._combo_css())
        form.addRow(theme_lbl, self._theme_combo)
        return page

    def _page_providers(self) -> QtWidgets.QWidget:
        page, form = self._make_page("Providers")
        page.setStyleSheet(self._field_css())

        # Gemini API Key
        gemini_lbl = QtWidgets.QLabel("Gemini API Key:")
        gemini_lbl.setStyleSheet(self._lbl_css())
        key_row = QtWidgets.QHBoxLayout()
        self._gemini_key = QtWidgets.QLineEdit()
        self._gemini_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._gemini_key.setPlaceholderText("AIza…")
        show_btn = QtWidgets.QPushButton("Show")
        show_btn.setFixedWidth(50)
        show_btn.setCheckable(True)
        show_btn.setStyleSheet(self._btn_css("#21262d", "#2d333b"))
        show_btn.toggled.connect(
            lambda chk: self._gemini_key.setEchoMode(
                QtWidgets.QLineEdit.Normal if chk else QtWidgets.QLineEdit.Password
            )
        )
        key_row.addWidget(self._gemini_key, 1)
        key_row.addWidget(show_btn)
        form.addRow(gemini_lbl, key_row)

        # Ollama URL
        ollama_lbl = QtWidgets.QLabel("Ollama URL:")
        ollama_lbl.setStyleSheet(self._lbl_css())
        self._ollama_url = QtWidgets.QLineEdit()
        self._ollama_url.setPlaceholderText("http://localhost:11434")
        form.addRow(ollama_lbl, self._ollama_url)
        return page

    def _page_editor(self) -> QtWidgets.QWidget:
        page, form = self._make_page("Editor")
        page.setStyleSheet(self._field_css())

        # Font size
        font_lbl = QtWidgets.QLabel("Font Size:")
        font_lbl.setStyleSheet(self._lbl_css())
        self._font_size = QtWidgets.QSpinBox()
        self._font_size.setRange(8, 32)
        self._font_size.setValue(13)
        form.addRow(font_lbl, self._font_size)

        # Tab width
        tab_lbl = QtWidgets.QLabel("Tab Width:")
        tab_lbl.setStyleSheet(self._lbl_css())
        self._tab_width = QtWidgets.QSpinBox()
        self._tab_width.setRange(2, 8)
        self._tab_width.setValue(4)
        form.addRow(tab_lbl, self._tab_width)

        # Word wrap
        wrap_lbl = QtWidgets.QLabel("Word Wrap:")
        wrap_lbl.setStyleSheet(self._lbl_css())
        self._word_wrap = QtWidgets.QCheckBox("Enable")
        self._word_wrap.setStyleSheet("color:#e6edf3; font-size:12px;")
        form.addRow(wrap_lbl, self._word_wrap)
        return page

    def _page_shortcuts(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        vlay = QtWidgets.QVBoxLayout(page)
        vlay.setContentsMargins(24, 20, 24, 20)
        vlay.setSpacing(10)

        lbl = QtWidgets.QLabel("Keyboard Shortcuts")
        lbl.setStyleSheet("color:#e6edf3; font-size:14px; font-weight:bold;")
        vlay.addWidget(lbl)
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color:#30363d;")
        vlay.addWidget(sep)

        shortcuts = [
            ("Save File",      "Ctrl+S"),
            ("New File",       "Ctrl+N"),
            ("Open Folder",    "Ctrl+K, Ctrl+O"),
            ("Run Code",       "F5"),
            ("AI Edit",        "Ctrl+Shift+E"),
            ("Explain Code",   "Ctrl+Shift+X"),
            ("Toggle Terminal","Ctrl+`"),
            ("Go to Def.",     "F12"),
            ("Rename Symbol",  "F2"),
            ("Settings",       "Ctrl+,"),
        ]
        tbl = QtWidgets.QTableWidget(len(shortcuts), 2)
        tbl.setHorizontalHeaderLabels(["Action", "Shortcut"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().hide()
        tbl.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        tbl.setSelectionMode(QtWidgets.QTableWidget.NoSelection)
        tbl.setStyleSheet("""
            QTableWidget {
                background:#0d1117; color:#e6edf3;
                border:1px solid #30363d; font-size:11px; gridline-color:#21262d;
            }
            QHeaderView::section {
                background:#161b22; color:#8b949e;
                padding:4px; border:none; font-size:11px;
            }
            QTableWidget::item { padding:5px 8px; }
        """)
        for row, (action, key) in enumerate(shortcuts):
            tbl.setItem(row, 0, QtWidgets.QTableWidgetItem(action))
            tbl.setItem(row, 1, QtWidgets.QTableWidgetItem(key))
        vlay.addWidget(tbl, 1)
        return page

    def _page_model(self) -> QtWidgets.QWidget:
        page, form = self._make_page("Model")

        model_lbl = QtWidgets.QLabel("Default Model:")
        model_lbl.setStyleSheet(self._lbl_css())
        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setStyleSheet(self._combo_css())
        for m in [
            "qwen2.5-coder:3b", "qwen2.5-coder:7b", "deepseek-coder",
            "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro",
        ]:
            self._model_combo.addItem(m)
        form.addRow(model_lbl, self._model_combo)
        return page

    def _page_generation(self) -> QtWidgets.QWidget:
        page, form = self._make_page("Generation")
        page.setStyleSheet(self._field_css())

        # Temperature
        temp_lbl = QtWidgets.QLabel("Temperature:")
        temp_lbl.setStyleSheet(self._lbl_css())
        temp_row = QtWidgets.QHBoxLayout()
        self._temp_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._temp_slider.setRange(0, 200)
        self._temp_slider.setValue(20)
        self._temp_slider.setStyleSheet("""
            QSlider::groove:horizontal { height:4px; background:#21262d; border-radius:2px; }
            QSlider::sub-page:horizontal { background:#58a6ff; border-radius:2px; }
            QSlider::handle:horizontal {
                background:#58a6ff; border-radius:6px;
                width:12px; height:12px; margin:-4px 0;
            }
        """)
        self._temp_val = QtWidgets.QLabel("0.20")
        self._temp_val.setStyleSheet("color:#58a6ff; font-size:12px; min-width:36px;")
        self._temp_slider.valueChanged.connect(
            lambda v: self._temp_val.setText(f"{v / 100:.2f}")
        )
        temp_row.addWidget(self._temp_slider, 1)
        temp_row.addWidget(self._temp_val)
        form.addRow(temp_lbl, temp_row)

        # Max tokens
        tok_lbl = QtWidgets.QLabel("Max Tokens:")
        tok_lbl.setStyleSheet(self._lbl_css())
        self._max_tokens = QtWidgets.QSpinBox()
        self._max_tokens.setRange(256, 32768)
        self._max_tokens.setSingleStep(256)
        self._max_tokens.setValue(4096)
        form.addRow(tok_lbl, self._max_tokens)
        return page

    # ── Value load / save ─────────────────────────────────────────────────────

    def _load_values(self) -> None:
        cfg = self.config

        # Providers
        gemini_key = (
            cfg.get("gemini_api_key", "")
            or cfg.get("providers", {}).get("gemini", {}).get("api_key", "")
        )
        self._gemini_key.setText(gemini_key)
        ollama_url = cfg.get("providers", {}).get("ollama", {}).get(
            "base_url", "http://localhost:11434"
        )
        self._ollama_url.setText(ollama_url)

        # Model
        model = cfg.get("model", "qwen2.5-coder:3b")
        idx = self._model_combo.findText(model)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)

        # Generation
        self._temp_slider.setValue(int(cfg.get("temperature", 0.2) * 100))
        self._max_tokens.setValue(cfg.get("max_tokens", 4096))

        # Editor
        editor = cfg.get("editor", {})
        self._font_size.setValue(editor.get("font_size", 13))
        self._tab_width.setValue(editor.get("tab_width", 4))
        self._word_wrap.setChecked(editor.get("word_wrap", False))

    def _collect_values(self) -> Dict[str, Any]:
        """Read widgets into a new config dict."""
        cfg: Dict[str, Any] = dict(self.config)

        # Providers
        gemini_key = self._gemini_key.text().strip()
        if gemini_key:
            cfg["gemini_api_key"] = gemini_key
            cfg.setdefault("providers", {}).setdefault("gemini", {})["api_key"] = gemini_key
        ollama_url = self._ollama_url.text().strip()
        if ollama_url:
            cfg.setdefault("providers", {}).setdefault("ollama", {})["base_url"] = ollama_url

        # Model
        cfg["model"] = self._model_combo.currentText()

        # Generation
        cfg["temperature"] = round(self._temp_slider.value() / 100.0, 2)
        cfg["max_tokens"]  = self._max_tokens.value()

        # Editor
        cfg.setdefault("editor", {})["font_size"]  = self._font_size.value()
        cfg.setdefault("editor", {})["tab_width"]   = self._tab_width.value()
        cfg.setdefault("editor", {})["word_wrap"]   = self._word_wrap.isChecked()

        return cfg

    def _apply(self) -> None:
        """Persist settings to config.json and apply live — no restart needed."""
        new_cfg = self._collect_values()
        self.config = new_cfg
        self.main_window.config = new_cfg
        try:
            from packager.packager import ConfigManager
            ConfigManager().save(new_cfg)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, "Save Error", f"Could not write config.json:\n{exc}"
            )
            return
        self.main_window.set_config(new_cfg)
        self._apply_btn.setText("✓ Applied")
        QtCore.QTimer.singleShot(1500, lambda: self._apply_btn.setText("Apply"))

    def _ok(self) -> None:
        self._apply()
        self.accept()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_cat_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    # ── Style helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _lbl_css() -> str:
        return "color:#8b949e; font-size:12px;"

    @staticmethod
    def _btn_css(bg: str, hover: str) -> str:
        return (
            f"QPushButton {{ background:{bg}; color:white; border:none;"
            f"border-radius:4px; padding:6px 18px; font-size:12px; }}"
            f"QPushButton:hover {{ background:{hover}; }}"
        )

    @staticmethod
    def _combo_css() -> str:
        return (
            "QComboBox { background:#21262d; color:#e6edf3;"
            "border:1px solid #30363d; border-radius:4px; padding:4px 8px; }"
        )

    @staticmethod
    def _field_css() -> str:
        return (
            "QLineEdit, QSpinBox, QDoubleSpinBox {"
            "background:#21262d; color:#e6edf3; border:1px solid #30363d;"
            "border-radius:4px; padding:4px 8px; font-size:12px; }"
            "QLineEdit:focus, QSpinBox:focus { border-color:#58a6ff; }"
        )
