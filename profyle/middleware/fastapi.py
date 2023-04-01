import tempfile
import json

from starlette.types import ASGIApp, Scope, Receive, Send
from viztracer import VizTracer

from profyle.database.sql_lite import store_trace
from profyle.models.trace import Trace
from profyle.deps.get_connection import get_connection



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
            self.tracer.start()
            await self.app(scope, receive, send)
            self.tracer.stop()
            self.tracer.save(tf.name)

        start = min(
            trace.get('ts')
            for trace in self.tracer.data.get('traceEvents', [])
            if trace.get('ts')
        )
        end = max(
            trace.get('ts', 0)
            for trace in self.tracer.data.get('traceEvents', [])
        )

        trace = Trace(
            data=json.dumps(self.tracer.data),
            duration=end-start,
            name=scope['path'],
        )
        db = get_connection()
        store_trace(trace, db)
