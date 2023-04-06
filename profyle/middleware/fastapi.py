import json

from starlette.types import ASGIApp, Scope, Receive, Send

from profyle.database.sql_lite import store_trace
from profyle.models.trace import Trace
from profyle.deps.get_connection import get_connection
from profyle.models.profyle import Profyle


class ProfileMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        enable: bool = True,
    ):

        self.app = app
        self.enable = enable
        if self.enable:
            self.profyle = Profyle()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:

        if scope['type'] != 'http' or not self.enable:
            await self.app(scope, receive, send)
            return

        with self.profyle:
            await self.app(scope, receive, send)

        trace = Trace(
            data=json.dumps(self.profyle.data),
            name=scope['path'],
        )
        db = get_connection()
        store_trace(trace, db)
