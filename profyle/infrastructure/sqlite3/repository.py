import json
from sqlite3 import Connection, Error, Row

from profyle.domain.trace import RecordedRequest, Trace, TraceCreate
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.sqlite3.get_connection import get_connection


class SQLiteTraceRepository(TraceRepository):
    def __init__(self, db: Connection | None = None):
        if not db:
            db = get_connection()
        self.db = db
        # Readers (CLI, MCP server) may open the database before the app wrote anything.
        self.create_trace_table()
        self.create_trace_selected_table()

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
                name VARCHAR(64) NOT NULL,
                request JSON
            );
            """
        )
        # Databases created by older versions have no `request` column.
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(traces)")}
        if "request" not in columns:
            cursor.execute("ALTER TABLE traces ADD COLUMN request JSON")
            self.db.commit()

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
            data_tuple = (1, trace_id)
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
                ( data, duration, name, request) VALUES (?, ?, ?, ?)
            """

            data_tuple = (
                json.dumps(trace.raw_trace),
                trace.duration,
                trace.name,
                trace.request.model_dump_json() if trace.request else None,
            )
            cursor.execute(insert_query, data_tuple)
            self.db.commit()
            cursor.close()

        except Error as error:
            print("Failed to insert data into trace table", error)

    def update_trace_request(self, trace_id: int, request: RecordedRequest) -> None:
        cursor = self.db.cursor()
        cursor.execute(
            "UPDATE traces SET request = ? WHERE id = ?",
            (request.model_dump_json(), trace_id),
        )
        self.db.commit()
        cursor.close()

    def get_all_traces(self) -> list[Trace]:
        self.db.row_factory = Row
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT
            id, timestamp, duration, name, request
            FROM traces
            ORDER BY timestamp DESC, id DESC
        """)

        traces = []
        for row in cursor.fetchall():
            trace = dict(row)
            if isinstance(trace.get("request"), str):
                trace["request"] = json.loads(trace["request"])
            traces.append(Trace(**trace))
        return traces

    def get_trace_by_id(self, id: int) -> Trace|None:
        self.db.row_factory = Row
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM traces where id = ?", (id,))
        trace = cursor.fetchone()
        if trace:
            trace_dict = dict(trace)
            for column in ("data", "request"):
                if isinstance(trace_dict.get(column), str):
                    trace_dict[column] = json.loads(trace_dict[column])
            return Trace(**trace_dict)

    def get_trace_selected(self) -> int|None:
        self.db.row_factory = Row
        cursor = self.db.cursor()
        cursor.execute("SELECT trace_id FROM trace_selected where id = ?", (1,))
        trace = cursor.fetchone()
        return trace["trace_id"] if trace else None

    def delete_trace_by_id(self, trace_id: int):
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM traces WHERE id = ?
            """,
            (trace_id,),
        )
        self.db.commit()
        cursor.close()
