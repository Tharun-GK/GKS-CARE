from contextlib import contextmanager
from pathlib import Path
import sqlite3


SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(database_path):
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def transaction(database_path):
    connection = connect(database_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path):
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect(database_path)
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        connection.close()
