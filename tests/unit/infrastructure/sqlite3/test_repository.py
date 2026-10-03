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


def test_stores_digest_and_loads_metadata_without_data(tmp_path):
    repo = SQLiteTraceRepository(sqlite3.connect(tmp_path / "p.db", check_same_thread=False))
    repo.store_trace(TraceCreate(raw_trace={"traceEvents": [], "big": "x"}, name="GET /a"))

    assert repo.trace_ids_without_digest(10) == [1]
    repo.store_digest(1, {"version": 1, "total_ms": 3}, "hot: f 3 ms")

    assert repo.trace_ids_without_digest(10) == []
    assert repo.get_digest(1) == {"version": 1, "total_ms": 3}
    meta = repo.get_trace_by_id(1, include_data=False)
    assert meta.data is None and meta.headline == "hot: f 3 ms"
    assert repo.get_all_traces()[0].headline == "hot: f 3 ms"
    assert repo.get_trace_by_id(1).data["big"] == "x"


def test_selection_request_update_and_cleanup(tmp_path):
    repo = SQLiteTraceRepository(sqlite3.connect(tmp_path / "p.db", check_same_thread=False))
    trace_id = repo.store_trace(TraceCreate(raw_trace={"traceEvents": []}, name="GET /a"))

    repo.store_trace_selected(trace_id)
    assert repo.get_trace_selected() == trace_id

    request = RecordedRequest(method="GET", path="/a", base_url="http://localhost")
    repo.update_trace_request(trace_id, request)
    assert repo.get_trace_by_id(trace_id).request == request
    assert repo.get_runtime() is None

    assert repo.deleted_all_selected_traces() == 1
    assert repo.delete_all_traces() == 1
    repo.vacuum()
    assert repo.get_all_traces() == []


def test_storage_errors_are_reported_not_raised(tmp_path, capsys):
    repo = SQLiteTraceRepository(sqlite3.connect(tmp_path / "p.db", check_same_thread=False))
    repo.db.close()

    assert repo.store_trace(TraceCreate(raw_trace={}, name="GET /a")) is None
    repo.store_trace_selected(1)

    out = capsys.readouterr().out
    assert "Failed to insert data into trace table" in out
    assert "Failed to insert data into selected_trace table" in out
