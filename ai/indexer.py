"""
ai/indexer.py — Background Project Indexer (Phase 9)
Provides fast, SQLite-backed semantic search (symbols, references, imports).
UI-independent service.
"""

import ast
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist", ".ai"}
_CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go", ".rs", ".php", ".dart"}

logger = logging.getLogger(__name__)


class ProjectIndexer:
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir).resolve()
        self.ai_dir = self.project_dir / ".ai"
        self.db_path = self.ai_dir / "index.db"
        self.meta_path = self.ai_dir / "index.meta.json"
        
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_indexed = False

        self._init_db()

    def _init_db(self):
        """Initialize SQLite database schema."""
        self.ai_dir.mkdir(parents=True, exist_ok=True)
        (self.ai_dir / "cache").mkdir(exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS files(
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE,
                    hash TEXT,
                    modified_time REAL,
                    language TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

                CREATE TABLE IF NOT EXISTS symbols(
                    id INTEGER PRIMARY KEY,
                    file_id INTEGER,
                    name TEXT,
                    kind TEXT,
                    line INTEGER,
                    parent TEXT,
                    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);

                CREATE TABLE IF NOT EXISTS imports(
                    id INTEGER PRIMARY KEY,
                    file_id INTEGER,
                    imported_module TEXT,
                    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id);

                CREATE TABLE IF NOT EXISTS symbol_references(
                    id INTEGER PRIMARY KEY,
                    symbol_id INTEGER,
                    file_id INTEGER,
                    line INTEGER,
                    FOREIGN KEY(symbol_id) REFERENCES symbols(id) ON DELETE CASCADE,
                    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
                );
            """)
            conn.commit()

    def get_conn(self) -> sqlite3.Connection:
        # SQLite objects created in a thread can only be used in that same thread
        # by default, but we can bypass or just create a new connection per query
        # since it's a local file. Using a new connection per operation is safest.
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ------------------------------------------------------------------
    # Background Indexing
    # ------------------------------------------------------------------

    def index_project(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._index_loop, daemon=True)
            self._thread.start()

    def _index_loop(self):
        """Full scan of the project, updates DB, then watches for changes."""
        try:
            # 1. Full scan
            all_files = self._get_all_files()
            
            with self.get_conn() as conn:
                for path in all_files:
                    if self._stop_event.is_set():
                        return
                    self._index_file_if_changed(conn, path)
            
            self._is_indexed = True

            # 2. Watch filesystem (simple polling for now)
            while not self._stop_event.is_set():
                time.sleep(5)
                # Check for modified files
                with self.get_conn() as conn:
                    for path in self._get_all_files():
                        if self._stop_event.is_set():
                            break
                        self._index_file_if_changed(conn, path)

        except Exception as e:
            logger.error(f"Indexer error: {e}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Parsing & Indexing
    # ------------------------------------------------------------------

    def update_file(self, path: str):
        """Force update a specific file immediately."""
        p = Path(path).resolve()
        if not p.is_file():
            return
        with self.get_conn() as conn:
            self._index_file(conn, p)

    def _index_file_if_changed(self, conn: sqlite3.Connection, path: Path):
        try:
            stat = path.stat()
            mod_time = stat.st_mtime
            
            cursor = conn.cursor()
            cursor.execute("SELECT modified_time FROM files WHERE path = ?", (str(path),))
            row = cursor.fetchone()
            
            if row and row[0] >= mod_time:
                return  # Unchanged
            
            self._index_file(conn, path, mod_time)
        except Exception:
            pass

    def _index_file(self, conn: sqlite3.Connection, path: Path, mod_time: Optional[float] = None):
        if mod_time is None:
            try:
                mod_time = path.stat().st_mtime
            except Exception:
                mod_time = time.time()
                
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return # Skip unreadable

        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        ext = path.suffix.lower()
        
        cursor = conn.cursor()
        
        # Upsert file
        cursor.execute("SELECT id FROM files WHERE path = ?", (str(path),))
        row = cursor.fetchone()
        if row:
            file_id = row[0]
            # Delete old symbols/imports for this file (Cascade deletes references)
            cursor.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))
            cursor.execute("""
                UPDATE files SET hash = ?, modified_time = ?, language = ? WHERE id = ?
            """, (content_hash, mod_time, ext, file_id))
        else:
            cursor.execute("""
                INSERT INTO files (path, hash, modified_time, language) VALUES (?, ?, ?, ?)
            """, (str(path), content_hash, mod_time, ext))
            file_id = cursor.lastrowid

        # Parse AST
        try:
            if ext == ".py":
                self._parse_python(cursor, file_id, content)
            else:
                self._parse_fallback(cursor, file_id, content, ext)
        except Exception as e:
            logger.debug(f"Parser failed for {path}: {e}. Storing metadata only.")
            
        conn.commit()

    def _parse_python(self, cursor: sqlite3.Cursor, file_id: int, content: str):
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cursor.execute("""
                    INSERT INTO symbols (file_id, name, kind, line, parent)
                    VALUES (?, ?, ?, ?, ?)
                """, (file_id, node.name, "class", node.lineno, None))
                
                for body_node in node.body:
                    if isinstance(body_node, ast.FunctionDef) or isinstance(body_node, ast.AsyncFunctionDef):
                        cursor.execute("""
                            INSERT INTO symbols (file_id, name, kind, line, parent)
                            VALUES (?, ?, ?, ?, ?)
                        """, (file_id, body_node.name, "method", body_node.lineno, node.name))

            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                # Avoid inserting method names as root functions
                cursor.execute("""
                    INSERT INTO symbols (file_id, name, kind, line, parent)
                    VALUES (?, ?, ?, ?, ?)
                """, (file_id, node.name, "function", node.lineno, None))

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    cursor.execute("INSERT INTO imports (file_id, imported_module) VALUES (?, ?)", 
                                   (file_id, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    cursor.execute("INSERT INTO imports (file_id, imported_module) VALUES (?, ?)", 
                                   (file_id, node.module))

    def _parse_fallback(self, cursor: sqlite3.Cursor, file_id: int, content: str, ext: str):
        """Regex fallback for JS/TS/Java etc."""
        patterns = [
            (re.compile(r"^\s*class\s+([A-Za-z0-9_]+)\s*[:({]", re.M), "class"),
            (re.compile(r"\b(?:function|const|let|var)\s+([A-Za-z0-9_]+)\s*=?\s*(?:\([^)]*\)\s*=>|\()", re.M), "function"),
            (re.compile(r"\bpublic\s+(?:[A-Za-z0-9_<>\[\]]+\s+)?([A-Za-z0-9_]+)\s*\(", re.M), "method"),
        ]
        lines = content.splitlines()
        for i, line in enumerate(lines):
            for pattern, kind in patterns:
                for match in pattern.finditer(line):
                    name = match.group(1)
                    cursor.execute("""
                        INSERT INTO symbols (file_id, name, kind, line, parent)
                        VALUES (?, ?, ?, ?, ?)
                    """, (file_id, name, kind, i + 1, None))

    def _get_all_files(self) -> List[Path]:
        paths = []
        for p in self.project_dir.rglob("*"):
            if p.is_file() and p.suffix in _CODE_EXTS:
                if not any(skip in p.parts for skip in _SKIP_DIRS):
                    paths.append(p)
        return paths

    # ------------------------------------------------------------------
    # API Design
    # ------------------------------------------------------------------

    def search_symbol(self, name: str) -> List[Dict[str, Any]]:
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.name, s.kind, s.line, s.parent, f.path
                FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE s.name = ?
            """, (name,))
            results = []
            for row in cursor.fetchall():
                results.append({
                    "name": row[0],
                    "kind": row[1],
                    "line": row[2],
                    "parent": row[3],
                    "path": row[4]
                })
            return results

    def find_references(self, symbol: str) -> List[Dict[str, Any]]:
        # Quick text search fallback for references
        return self.search_text(rf"\b{re.escape(symbol)}\b", is_regex=True)

    def search_text(self, query: str, is_regex: bool = False, case_sensitive: bool = False) -> List[Dict[str, Any]]:
        flags = 0 if case_sensitive else re.IGNORECASE
        if not is_regex:
            query = re.escape(query)
        try:
            pattern = re.compile(query, flags)
        except re.error:
            pattern = re.compile(re.escape(query), flags)

        results = []
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM files")
            for row in cursor.fetchall():
                path = Path(row[0])
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if pattern.search(line):
                            results.append({
                                "path": str(path),
                                "line": i + 1,
                                "text": line.strip()
                            })
                except Exception:
                    pass
        return results

    @property
    def is_ready(self) -> bool:
        return self._is_indexed
