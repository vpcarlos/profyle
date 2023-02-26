from sqlite3 import Connection, Error, Row
from typing import List

from profyle.models.trace import Trace


def create_trace_table(db: Connection):
    cursor = db.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS trace (  
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, 
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, 
        file TEXT NOT NULL,
        duration REAL NOT NULL,
        name VARCHAR(64) NOT NULL,
        label VARCHAR(64) NOT NULL
    );
    """
    )

def remove_all_traces(db:Connection):
    cursor = db.cursor()
    cursor.execute(
        """
        DELETE FROM trace
        """
    )
    db.commit()
    cursor.close()
    return cursor.rowcount

def store_trace(trace: Trace, db: Connection) -> None:
    connection = False
    try:

        cursor = db.cursor()

        insert_query = """ 
            INSERT INTO trace
            ( file, duration, name, label) VALUES (?, ?, ?, ?)
        """

        data_tuple = (
            trace.file,
            trace.duration,
            trace.name,
            trace.label
        )
        cursor.execute(insert_query, data_tuple)
        db.commit()
        cursor.close()

    except Error as error:
        print("Failed to insert blob data into sqlite table", error)
    finally:
        if connection:
            connection.close()


def get_traces(db: Connection) -> List[Trace]:
    db.row_factory = Row
    cursor = db.cursor()
    cursor.execute("SELECT * FROM trace")

    traces = cursor.fetchall()
    return [
        Trace(**dict(trace))
        for trace in traces
    ]


def get_trace_by_id(id: str, db: Connection) -> Trace:
    db.row_factory = Row
    cursor = db.cursor()
    cursor.execute("SELECT * FROM trace where id = ?", (id,))
    trace = cursor.fetchone()
    return Trace(**dict(trace))
