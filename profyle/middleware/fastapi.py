import tempfile
from time import time
from starlette.types import ASGIApp, Scope, Receive, Send

from profyle.database.sql_lite import store_trace
from profyle.models.trace import Trace
from profyle.deps.get_connection import get_connection
from viztracer import VizTracer


class ProfileMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        enable: bool = True,
        sort_by: str = 'cumulative',
    ):

        self.app = app
        self.enable = enable
        if enable:
            self.tracer = VizTracer()
            self.sort_by = sort_by

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:

        if scope['type'] != 'http' or not self.enable:
            await self.app(scope, receive, send)
            return
        with tempfile.NamedTemporaryFile(suffix='.json') as tf:
            start = time()
            self.tracer.start()
            await self.app(scope, receive, send)
            self.tracer.stop()
            end = time()
            self.tracer.save(tf.name)

        trace = Trace(
            data=self.tracer.data,
            duration=end-start,
            name=scope['path'],
        )
        db = get_connection()
        store_trace(trace, db)
