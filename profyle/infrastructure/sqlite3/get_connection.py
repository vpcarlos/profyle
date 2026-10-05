import os
import sqlite3
from sqlite3 import Connection

from profyle.settings import settings


def get_connection() -> Connection:
    db_path = settings.get_db_path()
    ensure_data_dir(os.path.dirname(db_path))
    db = sqlite3.connect(db_path, check_same_thread=False)
    return db


def ensure_data_dir(path: str) -> None:
    """Create the traces directory, ignored by git so traces are never committed."""
    if not path or os.path.isdir(path):
        return
    os.makedirs(path, exist_ok=True)
    if os.path.basename(path) == ".profyle":
        with open(os.path.join(path, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("# Created by Profyle: traces may contain source code and request data.\n*\n")
