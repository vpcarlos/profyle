from sqlite3 import Connection
import tempfile
import json
from types import TracebackType
from typing import Optional, Type

from viztracer import VizTracer
from profyle.database.sql_lite import store_trace
from profyle.deps.get_connection import get_connection

from profyle.models.trace import Trace


class profyle:

    def __init__(
        self,
        name: str,
        tracer: VizTracer = VizTracer(),
        db: Connection = get_connection()
    ) -> None:
        self.name = name
        self.tracer = tracer
        self.db = db

    def __enter__(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.json')
        self.tracer.start()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ):
        self.tracer.stop()
        self.tracer.save(self.temp_file.name)
        self.temp_file.close()
        self.data = self.tracer.data

        trace = Trace(
            data=json.dumps(self.data),
            name=self.name,
        )

        store_trace(trace, self.db)
