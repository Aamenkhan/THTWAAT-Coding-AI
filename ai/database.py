"""
ai/database.py — SQLite Conversation and Logging Database (Phase 11)
Stores chat history, timestamps, and robust request logs.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
import json
from typing import List, Dict, Any, Optional

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with self._get_conn() as conn:
            # Conversations table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT
                )
            ''')
            # Raw Logs table (for debugging and transparency)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_prompt TEXT,
                    provider_request TEXT,
                    provider_response TEXT,
                    error TEXT,
                    timestamp TEXT
                )
            ''')
            conn.commit()

    def add_message(self, role: str, content: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO messages (role, content, timestamp) VALUES (?, ?, ?)",
                (role, content, datetime.now().isoformat())
            )
            conn.commit()
            
    def get_messages(self, limit: int = 50) -> List[Dict[str, str]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT role, content, timestamp FROM messages ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]
            
    def log_request(self, user_prompt: str, request_data: str, response_data: str, error: str = ""):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO request_logs (user_prompt, provider_request, provider_response, error, timestamp) VALUES (?, ?, ?, ?, ?)",
                (user_prompt, request_data, response_data, error, datetime.now().isoformat())
            )
            conn.commit()

    def search_messages(self, query: str) -> List[Dict[str, str]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT role, content, timestamp FROM messages WHERE content LIKE ? ORDER BY id DESC LIMIT 50",
                (f"%{query}%",)
            )
            rows = cursor.fetchall()
            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]
