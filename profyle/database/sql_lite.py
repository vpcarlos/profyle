from sqlite3 import Connection, Error, Row
from typing import List, Optional
import json

from profyle.models.trace import Trace


def create_select_trace(db: Connection) -> None:
    cursor = db.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS select_trace (
            id INTEGER PRIMARY KEY NOT NULL,   
            trace_id INTEGER
        );
        """
    )


def create_trace_table(db: Connection) -> None:
    cursor = db.cursor()
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


def remove_all_traces(db: Connection) -> int:
    cursor = db.cursor()
    cursor.execute(
        """
        DELETE FROM traces
        """
    )
    db.commit()
    cursor.close()
    return cursor.rowcount


def vacuum(db: Connection) -> None:
    cursor = db.cursor()
    cursor.execute(
        """
        VACUUM
        """
    )
    db.commit()
    cursor.close()


def store_select_trace(trace_id: int, db: Connection) -> None:
    try:
        cursor = db.cursor()
        replace_query = """ 
                REPLACE INTO select_trace
                ( id, trace_id) VALUES (?, ?)
            """
        data_tuple = (
            1,
            trace_id
        )
        cursor.execute(replace_query, data_tuple)
        db.commit()
        cursor.close()
    except Error as error:
        print("Failed to insert blob data into sqlite table", error)


def store_trace(trace: Trace, db: Connection) -> None:
    connection = False
    try:

        cursor = db.cursor()

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
        db.commit()
        cursor.close()

    except Error as error:
        print("Failed to insert blob data into sqlite table", error)
    finally:
        if connection:
            connection.close()


def get_all_traces(db: Connection) -> List[Trace]:
    db.row_factory = Row
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, timestamp, duration, name FROM traces ORDER BY timestamp DESC")

    traces = cursor.fetchall()

    return [
        Trace(**dict(trace))
        for trace in traces
    ]


def get_trace_by_id(id: int, db: Connection) -> Optional[Trace]:
    db.row_factory = Row
    cursor = db.cursor()
    cursor.execute("SELECT * FROM traces where id = ?", (id,))
    trace = cursor.fetchone()
    if trace:
        return Trace(**dict(trace))


def get_select_trace(db: Connection) -> Optional[int]:
    db.row_factory = Row
    cursor = db.cursor()
    cursor.execute("SELECT trace_id FROM select_trace where id = ?", (1,))
    trace = cursor.fetchone()
    return trace['trace_id'] if trace else None
