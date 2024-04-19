import json
from sqlite3 import Connection, Error, Row

from profyle.domain.trace import Trace, TraceCreate
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.sqlite3.get_connection import get_connection


class SQLiteTraceRepository(TraceRepository):
    def __init__(self, db: Connection | None = None):
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

    def create_trace_file_table(self) -> None:
        cursor = self.db.cursor()
        # trace_id is a foreign key to the traces table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_files (
                trace_id VARCHAR(64) PRIMARY KEY NOT NULL,
                FOREIGN KEY (trace_id) REFERENCES traces(id),
                path VARCHAR(400) NOT NULL,
                source_code TEXT NOT NULL,
                line_count INTEGER NOT NULL,
            );
            """
        )
        self.db.commit()
        cursor.close()

    def create_trace_function_table(self) -> None:
        cursor = self.db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_functions (
                trace_id VARCHAR(64) PRIMARY KEY NOT NULL,
                FOREIGN KEY (trace_id) REFERENCES traces(id),
                name VARCHAR(400) NOT NULL,
                file_path VARCHAR(400) NOT NULL,
                line_number INTEGER NOT NULL,
            );
            """
        )
        self.db.commit()
        cursor.close()

    def create_trace_event_table(self) -> None:
        cursor = self.db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_events (
                trace_id VARCHAR(64) PRIMARY KEY NOT NULL,
                FOREIGN KEY (trace_id) REFERENCES traces(id),
                phase_type VARCHAR(10) NOT NULL,
                process_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                duration REAL NOT NULL,
                name VARCHAR(400) NOT NULL,
                args TEXT NOT NULL,
                category VARCHAR(400) NOT NULL,
            );
            """
        )
        self.db.commit()
        cursor.close()

    def create_trace_metadata_table(self) -> None:
        cursor = self.db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_metadata (
                trace_id VARCHAR(64) PRIMARY KEY NOT NULL,
                FOREIGN KEY (trace_id) REFERENCES traces(id),
                metadata TEXT NOT NULL,
            );
            """
        )
        self.db.commit()
        cursor.close()

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

    def delete_all_trace_files(self) -> int:
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM trace_files
            """
        )
        self.db.commit()
        cursor.close()
        return cursor.rowcount

    def delete_all_trace_functions(self) -> int:
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM trace_functions
            """
        )
        self.db.commit()
        cursor.close()
        return cursor.rowcount

    def delete_all_trace_events(self) -> int:
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM trace_events
            """
        )
        self.db.commit()
        cursor.close()
        return cursor.rowcount

    def delete_all_trace_metadata(self) -> int:
        cursor = self.db.cursor()
        cursor.execute(
            """
            DELETE FROM trace_metadata
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

        return [Trace(**dict(trace)) for trace in traces]

    def get_trace_by_id(self, id: int) -> Trace|None:
        self.db.row_factory = Row
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM traces where id = ?", (id,))
        trace = cursor.fetchone()
        if trace:
            trace_dict = dict(trace)
            if isinstance(trace_dict.get("data"), str):
                trace_dict["data"] = json.loads(trace_dict["data"])
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
