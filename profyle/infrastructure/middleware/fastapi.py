from typing import Optional
from starlette.types import ASGIApp, Scope, Receive, Send

from profyle.application.profyle import profyle
from profyle.infrastructure.sqlite3.get_connection import get_connection
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


class ProfyleMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        pattern: Optional[str] = None
    ):
        self.app = app
        self.enabled = enabled
        self.pattern = pattern

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.enabled and scope['type'] == 'http':
            db = get_connection()
            sqlite_repo = SQLiteTraceRepository(db)
            with profyle(
                name=scope['raw_path'].decode("utf-8"),
                pattern=self.pattern,
                repo=sqlite_repo
            ):
                await self.app(scope, receive, send)
            return
        await self.app(scope, receive, send)
