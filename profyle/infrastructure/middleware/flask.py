from typing import Optional
from profyle.application.profyle import profyle
from profyle.infrastructure.sqlite3.get_connection import get_connection
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


class ProfyleMiddleware:
    def __init__(
        self,
        app,
        enabled: bool = True,
        pattern: Optional[str] = None
    ):
        self.app = app
        self.enabled = enabled
        self.pattern = pattern

    def __call__(self, environ, start_response):
        if environ.get('wsgi.url_scheme') == 'http' and self.enabled:
            db = get_connection()
            sqlite_repo = SQLiteTraceRepository(db)
            with profyle(
                name=environ['REQUEST_URI'],
                pattern=self.pattern,
                repo=sqlite_repo
            ):
                return self.app(environ, start_response)
        return self.app(environ, start_response)
