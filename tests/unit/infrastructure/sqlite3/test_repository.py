import sqlite3

from profyle.domain.trace import RecordedRequest, TraceCreate
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


def test_migrates_old_databases_and_round_trips_the_request(tmp_path):
    db = sqlite3.connect(tmp_path / "profile.db", check_same_thread=False)
    db.execute(
        """CREATE TABLE traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            data JSON NOT NULL, duration REAL NOT NULL, name VARCHAR(64) NOT NULL)"""
    )
    db.execute("INSERT INTO traces (data, duration, name) VALUES ('{}', 1, 'GET /old')")
    db.commit()
    repo = SQLiteTraceRepository(db)

    repo.store_trace(
        TraceCreate(
            raw_trace={"traceEvents": []},
            name="GET /new",
            request=RecordedRequest(method="GET", path="/new", base_url="http://localhost"),
        )
    )

    old, new = repo.get_trace_by_id(1), repo.get_trace_by_id(2)
    assert old.request is None
    assert new.request.path == "/new"
