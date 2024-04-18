import json
from sqlite3 import Connection, Error, Row
from typing import Optional

from profyle.domain.trace import Trace, TraceCreate
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.sqlite3.get_connection import get_connection


class SQLiteTraceRepository(TraceRepository):
    def __init__(self, db: Optional[Connection] = None):
        if not db:
            db = get_connection()
        self.db = db

    def create_trace_selected_table(self) -> None:
        cursor = self.db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_selected (
                id INTEGER PRIMARY KEY NOT NULL,
                trace_id INTEGER
            );
            """
        )

    def create_trace_table(self) -> None:
        cursor = self.db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                data JSON NOT NULL,
                duration REAL NOT NULL,
                name VARCHAR(64) NOT NULL
            );
            """
        )

    def delete_all_traces(self) -> int:
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM traces
            """
        )
        self.db.commit()
        cursor.close()
        return cursor.rowcount

    def deleted_all_selected_traces(self) -> int:
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM trace_selected
            """
        )
        self.db.commit()
        cursor.close()
        return cursor.rowcount

    def vacuum(self) -> None:
        cursor = self.db.cursor()
        cursor.execute(
            """
            VACUUM
            """
        )
        self.db.commit()
        cursor.close()

    def store_trace_selected(self, trace_id: int) -> None:
        try:
            self.create_trace_selected_table()
            cursor = self.db.cursor()
            replace_query = """
                    REPLACE INTO trace_selected
                    ( id, trace_id) VALUES (?, ?)
                """
            data_tuple = (
                1,
                trace_id
            )
            cursor.execute(replace_query, data_tuple)
            self.db.commit()
            cursor.close()
        except Error as error:
            print("Failed to insert data into selected_trace table", error)

    def store_trace(self, trace: TraceCreate) -> None:
        try:
            self.create_trace_table()
            cursor = self.db.cursor()

            insert_query = """
                INSERT INTO traces
                ( data, duration, name) VALUES (?, ?, ?)
            """

            data_tuple = (
                json.dumps(trace.data),
                trace.duration,
                trace.name,
            )
            cursor.execute(insert_query, data_tuple)
            self.db.commit()
            cursor.close()

        except Error as error:
            print("Failed to insert data into trace table", error)

    def get_all_traces(self) -> list[Trace]:
        self.db.row_factory = Row
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT
            id, timestamp, duration, name
            FROM traces
            ORDER BY timestamp DESC
        """)

        traces = cursor.fetchall()

        return [
            Trace(**dict(trace))
            for trace in traces
        ]

    def get_trace_by_id(self, id: int) -> Optional[Trace]:
        self.db.row_factory = Row
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM traces where id = ?", (id,))
        trace = cursor.fetchone()
        if trace:
            return Trace(**dict(trace))

    def get_trace_selected(self) -> Optional[int]:
        self.db.row_factory = Row
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT trace_id FROM trace_selected where id = ?", (1,))
        trace = cursor.fetchone()
        return trace["trace_id"] if trace else None

    def delete_trace_by_id(self, trace_id: int):
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM traces WHERE id = ?
            """,
            (trace_id,)
        )
        self.db.commit()
        cursor.close()
