"""
state_db.py - Metadata State Table (SQLite)
This is the persistent record of every task's lifecycle.
It is the "source of truth" for fault recovery.
If the Master crashes and restarts, it can re-read state from here.
"""

import sqlite3
import threading
import time
import os
import json
import logging

logger = logging.getLogger("state_db")

DB_PATH = os.path.join(os.path.dirname(__file__), "task_state.db")


class StateDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id        TEXT PRIMARY KEY,
                    name           TEXT NOT NULL,
                    func           TEXT,
                    status         TEXT,
                    priority       INTEGER,
                    dependencies   TEXT,
                    assigned_worker TEXT,
                    created_at     REAL,
                    started_at     REAL,
                    completed_at   REAL,
                    result         TEXT,
                    error          TEXT,
                    retry_count    INTEGER DEFAULT 0,
                    args           TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id    TEXT,
                    event_type TEXT,
                    detail     TEXT,
                    timestamp  REAL
                )
            """)
            conn.commit()
        logger.info(f"StateDB initialized at {self.db_path}")

    def insert_task(self, task):
        with self._lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO tasks
                    (task_id, name, func, status, priority, dependencies,
                     assigned_worker, created_at, started_at, completed_at,
                     result, error, retry_count, args)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    task.task_id, task.name, task.func,
                    task.status.value, task.priority,
                    json.dumps(task.dependencies),
                    task.assigned_worker,
                    task.created_at, task.started_at, task.completed_at,
                    task.result, task.error, task.retry_count,
                    json.dumps(task.args)
                ))
                conn.commit()

    def update_task(self, task):
        """Update task state — called every time status changes."""
        with self._lock:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE tasks SET
                        status=?, assigned_worker=?, started_at=?,
                        completed_at=?, result=?, error=?, retry_count=?
                    WHERE task_id=?
                """, (
                    task.status.value, task.assigned_worker,
                    task.started_at, task.completed_at,
                    task.result, task.error, task.retry_count,
                    task.task_id
                ))
                conn.execute("""
                    INSERT INTO events (task_id, event_type, detail, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (
                    task.task_id,
                    task.status.value,
                    task.result or task.error or "",
                    time.time()
                ))
                conn.commit()

    def get_all_tasks(self) -> list:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def get_task_events(self, task_id: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY timestamp",
                (task_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def print_state_table(self):
        tasks = self.get_all_tasks()
        print("\n  [DB] Metadata State Table:")
        print(f"  {'NAME':<22} {'STATUS':<12} {'WORKER':<15} {'RETRIES':<8} {'RESULT'}")
        print("  " + "-" * 75)
        for t in tasks:
            result_preview = (t["result"] or t["error"] or "")[:30]
            print(
                f"  {t['name']:<22} {t['status']:<12} "
                f"{(t['assigned_worker'] or '-'):<15} "
                f"{t['retry_count']:<8} {result_preview}"
            )
        print()

    def clear(self):
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM tasks")
                conn.execute("DELETE FROM events")
                conn.commit()
        logger.info("StateDB cleared.")
