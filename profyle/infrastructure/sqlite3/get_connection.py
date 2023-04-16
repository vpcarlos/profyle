import sqlite3
from sqlite3 import Connection

from profyle.settings import settings


def get_connection() -> Connection:
    db = sqlite3.connect(
        settings.get_path('profile.db'),
        check_same_thread=False
    )
    return db
