from contextlib import closing, contextmanager
import argparse
import os
from pathlib import Path
import sqlite3
import tempfile


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


def _validate_database_integrity(database_path):
    with closing(sqlite3.connect(str(database_path))) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise sqlite3.DatabaseError(f"SQLite integrity check failed: {result}")


def _copy_database(source_path, destination_path):
    with closing(sqlite3.connect(str(source_path))) as source:
        with closing(sqlite3.connect(str(destination_path))) as destination:
            source.backup(destination)
    _validate_database_integrity(destination_path)


def _create_database_copy(source_path, destination_path):
    source_path = Path(source_path).resolve()
    destination_path = Path(destination_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source database does not exist: {source_path}")
    if source_path == destination_path:
        raise ValueError("SQLite source and destination paths must be different.")
    if destination_path.exists():
        raise FileExistsError(f"SQLite destination already exists: {destination_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination_path.parent,
            prefix=f".{destination_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        _copy_database(source_path, temporary_path)
        os.link(temporary_path, destination_path)
        temporary_path.unlink()
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination_path


def backup_database(source_path, backup_path):
    return _create_database_copy(source_path, backup_path)


def restore_database(backup_path, destination_path):
    return _create_database_copy(backup_path, destination_path)


def _run_database_command():
    parser = argparse.ArgumentParser(description="Back up or restore a GKS-CARE SQLite database.")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Create a consistent database backup.")
    backup.add_argument("source")
    backup.add_argument("destination")
    restore = commands.add_parser("restore", help="Restore a backup to a new database path.")
    restore.add_argument("source")
    restore.add_argument("destination")
    arguments = parser.parse_args()

    operation = backup_database if arguments.command == "backup" else restore_database
    result = operation(arguments.source, arguments.destination)
    print(f"SQLite {arguments.command} created: {result}")


if __name__ == "__main__":
    _run_database_command()
