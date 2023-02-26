import cProfile
import pstats

from starlette.types import ASGIApp, Scope, Receive, Send

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
            self.profiler = cProfile.Profile()
            self.sort_by = sort_by

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:

        if scope['type'] != 'http' or not self.enable:
            await self.app(scope, receive, send)
            return

        self.profiler.enable()
        await self.app(scope, receive, send)
        self.profiler.disable()

        ps = pstats.Stats(self.profiler).sort_stats(self.sort_by)

        trace = Trace(
            file=str(ps.stats),  # type: ignore
            duration=ps.total_tt,  # type: ignore
            label=scope['method'],
            name=scope['path'],
        )
        db = get_connection()
        store_trace(trace, db)
