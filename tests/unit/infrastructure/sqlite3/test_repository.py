import sqlite3

from profyle.domain.trace import NewTrace, RecordedRequest
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


def new_repo(tmp_path):
    return SQLiteTraceRepository(sqlite3.connect(tmp_path / "p.db", check_same_thread=False))


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

    repo.add_trace(
        NewTrace(
            raw_trace={"traceEvents": []},
            name="GET /new",
            request=RecordedRequest(method="GET", path="/new", base_url="http://localhost"),
        )
    )

    old, new = repo.get_trace(1), repo.get_trace(2)
    assert old.request is None
    assert new.request.path == "/new"


def test_stores_digest_and_loads_metadata_without_data(tmp_path):
    repo = new_repo(tmp_path)
    repo.add_trace(NewTrace(raw_trace={"traceEvents": [], "big": "x"}, name="GET /a"))

    assert repo.trace_ids_without_digest(10) == [1]
    repo.store_digest(1, {"version": 1, "total_ms": 3}, "hot: f 3 ms")

    assert repo.trace_ids_without_digest(10) == []
    assert repo.get_digest(1) == {"version": 1, "total_ms": 3}
    meta = repo.get_trace(1, include_data=False)
    assert meta.data is None and meta.headline == "hot: f 3 ms"
    assert repo.list_traces()[0].headline == "hot: f 3 ms"
    assert repo.get_trace(1).data["big"] == "x"
    assert repo.get_trace(99) is None


def test_lists_newest_first_with_filters_in_sql(tmp_path):
    repo = new_repo(tmp_path)
    slow = {"traceEvents": [{"ph": "X", "ts": 1, "dur": 5000}]}
    for name, trace in [("GET /a", slow), ("GET /B?x=1", slow), ("GET /b", {})]:
        repo.add_trace(NewTrace(raw_trace=trace, name=name))

    assert [t.name for t in repo.list_traces()] == ["GET /b", "GET /B?x=1", "GET /a"]
    assert [t.id for t in repo.list_traces(limit=1)] == [3]
    assert [t.id for t in repo.list_traces(name_contains="/b")] == [3, 2]
    assert [t.id for t in repo.list_traces(min_duration_ms=5)] == [2, 1]
    assert repo.list_traces(name_contains="%") == []  # not a wildcard
    assert repo.latest_trace_id() == 3


def test_request_update_runtime_and_cleanup(tmp_path):
    repo = new_repo(tmp_path)
    assert repo.latest_trace_id() == 0
    trace_id = repo.add_trace(NewTrace(raw_trace={"traceEvents": []}, name="GET /a"))
    repo.add_trace(NewTrace(raw_trace={"traceEvents": []}, name="GET /b"))

    assert repo.get_runtime() is None
    repo.store_runtime({"pid": 1})
    assert repo.get_runtime() == {"pid": 1}

    repo.delete_trace(trace_id)
    assert [t.name for t in repo.list_traces()] == ["GET /b"]
    assert repo.delete_all_traces() == 1
    assert repo.list_traces() == []


def test_storage_errors_are_reported_not_raised(tmp_path, capsys):
    repo = new_repo(tmp_path)
    repo.close()

    assert repo.add_trace(NewTrace(raw_trace={}, name="GET /a")) is None
    assert "could not store the trace of GET /a" in capsys.readouterr().err
