from PySide6 import QtCore, QtGui, QtWidgets
from pathlib import Path

from ai.workspace_search import WorkspaceSearch, SearchResult

class WorkspaceSearchPanel(QtWidgets.QWidget):
    # Signal emitted when a result is double-clicked: (file_path, line_number)
    result_selected = QtCore.Signal(str, int)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.search_backend = None
        
        self.setObjectName("WorkspaceSearchPanel")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Search Input
        self.search_input = QtWidgets.QLineEdit(self)
        self.search_input.setPlaceholderText("Search workspace... (Press Enter)")
        self.search_input.returnPressed.connect(self._perform_search)
        layout.addWidget(self.search_input)
        
        # Results Tree
        self.results_tree = QtWidgets.QTreeWidget(self)
        self.results_tree.setHeaderHidden(True)
        self.results_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.results_tree)

    def set_project_dir(self, project_dir: str):
        self.search_backend = WorkspaceSearch(project_dir)

    def _perform_search(self):
        query = self.search_input.text().strip()
        self.results_tree.clear()
        
        if not query or not self.search_backend:
            return
            
        # Optional: could run this in a QThread to prevent UI blocking for huge projects
        results = self.search_backend.project_wide_search(query)
        
        if not results:
            item = QtWidgets.QTreeWidgetItem(["No results found."])
            self.results_tree.addTopLevelItem(item)
            return
            
        # Group by file
        grouped_results = {}
        for res in results:
            if res.path not in grouped_results:
                grouped_results[res.path] = []
            grouped_results[res.path].append(res)
            
        for path, file_results in grouped_results.items():
            short_path = Path(path).name
            file_item = QtWidgets.QTreeWidgetItem([f"{short_path} ({len(file_results)})"])
            file_item.setToolTip(0, path)
            file_item.setData(0, QtCore.Qt.UserRole, "file")
            
            for res in file_results:
                # Truncate text if it's too long
                preview = res.text[:80] + ("..." if len(res.text) > 80 else "")
                match_item = QtWidgets.QTreeWidgetItem([f"Ln {res.line}: {preview}"])
                match_item.setData(0, QtCore.Qt.UserRole, (res.path, res.line))
                file_item.addChild(match_item)
                
            self.results_tree.addTopLevelItem(file_item)
            
        self.results_tree.expandAll()

    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        data = item.data(0, QtCore.Qt.UserRole)
        if isinstance(data, tuple):
            path, line = data
            self.result_selected.emit(path, line)
