import json
from sqlite3 import Connection, Error, Row
from typing import Any

from profyle.domain.trace import NewTrace, RecordedRequest, Trace
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.sqlite3.get_connection import get_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    data JSON NOT NULL,
    duration REAL NOT NULL,
    name TEXT NOT NULL,
    request JSON,
    digest JSON,
    headline TEXT
);
CREATE TABLE IF NOT EXISTS runtime (id INTEGER PRIMARY KEY, info JSON);
"""
# Columns added after the first release, for databases created by older versions.
ADDED_COLUMNS = {"request": "JSON", "digest": "JSON", "headline": "TEXT"}

# Every column but the (large) trace data.
SUMMARY_COLUMNS = "id, timestamp, duration, name, request, headline"


class SQLiteTraceRepository(TraceRepository):
    def __init__(self, db: Connection | None = None):
        self.db = db or get_connection()
        # File behind the connection ("" for in-memory databases).
        self.db_path: str = self.db.execute("PRAGMA database_list").fetchone()[2] or ""
        # Readers (CLI, MCP server) may open the database before the app wrote anything.
        self._create_schema()

    def close(self) -> None:
        self.db.close()

    def _create_schema(self) -> None:
        self.db.executescript(SCHEMA)
        columns = {row["name"] for row in self._query("PRAGMA table_info(traces)")}
        for column, kind in ADDED_COLUMNS.items():
            if column not in columns:
                self.db.execute(f"ALTER TABLE traces ADD COLUMN {column} {kind}")
        self.db.commit()

    def _query(self, sql: str, params: tuple = ()) -> list[Row]:
        cursor = self.db.cursor()
        cursor.row_factory = Row
        try:
            return cursor.execute(sql, params).fetchall()
        finally:
            cursor.close()

    def _change(self, sql: str, params: tuple = ()) -> int:
        """Run a statement that writes; returns the id of the inserted row for an
        INSERT, otherwise how many rows changed."""
        cursor = self.db.cursor()
        try:
            cursor.execute(sql, params)
            self.db.commit()
            return cursor.lastrowid if sql.lstrip().startswith("INSERT") else cursor.rowcount
        finally:
            cursor.close()

    # --- Traces ---------------------------------------------------------------------

    def add_trace(self, trace: NewTrace) -> int | None:
        try:
            return self._change(
                "INSERT INTO traces (data, duration, name, request) VALUES (?, ?, ?, ?)",
                (
                    json.dumps(trace.raw_trace),
                    trace.duration,
                    trace.name,
                    trace.request.model_dump_json() if trace.request else None,
                ),
            )
        except Error as error:
            # Losing one trace must never break the request that produced it.
            from profyle.infrastructure.console import say

            say(f"could not store the trace of {trace.name}: {error}")
            return None

    def get_trace(self, trace_id: int, include_data: bool = True) -> Trace | None:
        columns = SUMMARY_COLUMNS + (", data" if include_data else "")
        rows = self._query(f"SELECT {columns} FROM traces WHERE id = ?", (trace_id,))
        return _to_trace(rows[0]) if rows else None

    def list_traces(
        self,
        limit: int | None = None,
        name_contains: str | None = None,
        min_duration_ms: float = 0,
    ) -> list[Trace]:
        rows = self._query(
            f"SELECT {SUMMARY_COLUMNS} FROM traces "
            "WHERE instr(lower(name), lower(?)) > 0 AND duration >= ? "
            "ORDER BY id DESC LIMIT ?",
            (name_contains or "", min_duration_ms * 1000, -1 if limit is None else limit),
        )
        return [_to_trace(row) for row in rows]

    def latest_trace_id(self) -> int:
        return self._query("SELECT COALESCE(MAX(id), 0) AS id FROM traces")[0]["id"]

    def update_request(self, trace_id: int, request: RecordedRequest) -> None:
        self._change(
            "UPDATE traces SET request = ? WHERE id = ?",
            (request.model_dump_json(), trace_id),
        )

    def delete_trace(self, trace_id: int) -> None:
        self._change("DELETE FROM traces WHERE id = ?", (trace_id,))

    def delete_all_traces(self) -> int:
        deleted = self._change("DELETE FROM traces")
        self.db.execute("VACUUM")
        return deleted

    # --- Digests --------------------------------------------------------------------

    def get_digest(self, trace_id: int) -> dict[str, Any] | None:
        rows = self._query("SELECT digest FROM traces WHERE id = ?", (trace_id,))
        return json.loads(rows[0]["digest"]) if rows and rows[0]["digest"] else None

    def store_digest(self, trace_id: int, digest: dict[str, Any], headline: str) -> None:
        self._change(
            "UPDATE traces SET digest = ?, headline = ? WHERE id = ?",
            (json.dumps(digest), headline, trace_id),
        )

    def trace_ids_without_digest(self, limit: int) -> list[int]:
        rows = self._query(
            "SELECT id FROM traces WHERE digest IS NULL ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [row["id"] for row in rows]

    # --- Runtime --------------------------------------------------------------------

    def store_runtime(self, info: dict[str, Any]) -> None:
        self._change("REPLACE INTO runtime (id, info) VALUES (1, ?)", (json.dumps(info),))

    def get_runtime(self) -> dict[str, Any] | None:
        rows = self._query("SELECT info FROM runtime WHERE id = 1")
        return json.loads(rows[0]["info"]) if rows else None


def _to_trace(row: Row) -> Trace:
    values = dict(row)
    for column in ("data", "request"):
        if isinstance(values.get(column), str):
            values[column] = json.loads(values[column])
    return Trace(**values)
