"""SQLite backed print history.

One connection guarded by a lock. The worker thread writes, the UI thread
reads, and neither should ever block long enough to matter at this data volume.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from . import env
from .logging_setup import get as get_logger

log = get_logger("history")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    started     REAL NOT NULL,
    finished    REAL,
    path        TEXT NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    printer     TEXT NOT NULL,
    pages       INTEGER DEFAULT 0,
    sheets      INTEGER DEFAULT 0,
    copies      INTEGER DEFAULT 1,
    bytes       INTEGER DEFAULT 0,
    status      TEXT NOT NULL,
    error       TEXT,
    duration    REAL DEFAULT 0,
    options     TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_started ON jobs(started DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
"""


class History:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._path = env.data_dir() / "history.db"
        self._conn: sqlite3.Connection | None = None
        self._open()

    def _open(self) -> None:
        try:
            self._conn = sqlite3.connect(
                str(self._path), check_same_thread=False, timeout=5.0
            )
            self._conn.row_factory = sqlite3.Row
            with self._lock:
                self._conn.executescript(SCHEMA)
                self._conn.commit()
        except sqlite3.Error as exc:
            log.error("cannot open history db: %s", exc)
            self._conn = None

    # ------------------------------------------------------------------ writes

    def record_start(self, job: dict[str, Any]) -> None:
        if not self._conn:
            return
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT OR REPLACE INTO jobs
                       (id, started, path, name, kind, printer, pages, sheets,
                        copies, bytes, status, options)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        job["id"],
                        job.get("started", time.time()),
                        job.get("path", ""),
                        job.get("name", ""),
                        job.get("kind", ""),
                        job.get("printer", ""),
                        int(job.get("pages", 0)),
                        int(job.get("sheets", 0)),
                        int(job.get("copies", 1)),
                        int(job.get("bytes", 0)),
                        job.get("status", "printing"),
                        json.dumps(job.get("options", {})),
                    ),
                )
                self._conn.commit()
            except sqlite3.Error as exc:
                log.warning("history insert failed: %s", exc)

    def record_finish(
        self,
        job_id: str,
        status: str,
        error: str = "",
        pages: int = 0,
        sheets: int = 0,
        duration: float = 0.0,
    ) -> None:
        if not self._conn:
            return
        with self._lock:
            try:
                self._conn.execute(
                    """UPDATE jobs
                          SET status=?, error=?, finished=?, duration=?,
                              pages=MAX(pages, ?), sheets=MAX(sheets, ?)
                        WHERE id=?""",
                    (status, error, time.time(), duration, int(pages), int(sheets), job_id),
                )
                self._conn.commit()
            except sqlite3.Error as exc:
                log.warning("history update failed: %s", exc)

    # ------------------------------------------------------------------- reads

    def recent(
        self, limit: int = 300, search: str = "", status: str = "all"
    ) -> list[dict[str, Any]]:
        if not self._conn:
            return []
        clauses, params = [], []
        if search:
            clauses.append("(name LIKE ? OR printer LIKE ? OR path LIKE ?)")
            needle = f"%{search}%"
            params += [needle, needle, needle]
        if status and status != "all":
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM jobs {where} ORDER BY started DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                log.warning("history query failed: %s", exc)
                return []
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["options"] = json.loads(item.get("options") or "{}")
            except ValueError:
                item["options"] = {}
            out.append(item)
        return out

    def stats(self) -> dict[str, Any]:
        if not self._conn:
            return {"jobs": 0, "pages": 0, "sheets": 0}
        with self._lock:
            try:
                row = self._conn.execute(
                    """SELECT COUNT(*) AS jobs,
                              COALESCE(SUM(pages),0) AS pages,
                              COALESCE(SUM(sheets),0) AS sheets
                         FROM jobs WHERE status='done'"""
                ).fetchone()
                return dict(row) if row else {"jobs": 0, "pages": 0, "sheets": 0}
            except sqlite3.Error:
                return {"jobs": 0, "pages": 0, "sheets": 0}

    # ---------------------------------------------------------------- clean up

    def delete(self, job_id: str) -> None:
        if not self._conn:
            return
        with self._lock:
            try:
                self._conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
                self._conn.commit()
            except sqlite3.Error:
                pass

    def clear(self) -> None:
        if not self._conn:
            return
        with self._lock:
            try:
                self._conn.execute("DELETE FROM jobs")
                self._conn.commit()
                self._conn.execute("VACUUM")
            except sqlite3.Error:
                pass

    def prune(self, days: int) -> int:
        if not self._conn or days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        with self._lock:
            try:
                cur = self._conn.execute("DELETE FROM jobs WHERE started < ?", (cutoff,))
                self._conn.commit()
                return cur.rowcount or 0
            except sqlite3.Error:
                return 0


history = History()
