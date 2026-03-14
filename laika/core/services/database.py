import sqlite3
from pathlib import Path
from src.core.models import File
from src.core.utils import compute_hash


class Database:
    """
        Database wrapper class that communicates with a 
        sqlite3 database with a single table of files.
    """
    def __init__(self) -> None:
        self.__connection = sqlite3.connect('src/core/data/sqlite3.db', check_same_thread=False)
        self._cursor = self.__connection.cursor()

        self.__initialize_schema()


    def __initialize_schema(self) -> None:
        self._cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                hash TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                last_updated TEXT DEFAULT (datetime('now', 'localtime'))
            )
        ''')
    

    def upsert_file(self, path: str | Path) -> File:
        """
            Inserts a new file on the database 
            by receiving its path and reading 
            its metadata.
        """
        file = File(path=str(path), hash=None)

        with open(path.__str__(), 'r') as f:
            content = f.read()

        if content is not None:
            file.hash = compute_hash(content)

        args = (file.path, file.hash,)
        self._cursor.execute('''
            INSERT INTO files (path, hash) VALUES (?, ?)
                ON CONFLICT DO
            UPDATE SET hash = ? WHERE path = ?
        ''', (*args, *args[::-1]))
        self.__connection.commit()

        file.id = self._cursor.lastrowid
        return file


    def get_file_by_path(self, path: str | Path) -> File:
        self._cursor.execute(
            'SELECT * FROM files WHERE path = ?', (str(path),)
        )

        row = self._cursor.fetchone()
        return File.make_from(row)


    def get_file_by_id(self, id: int) -> File:
        self._cursor.execute(
            'SELECT * FROM files WHERE id = ?', (id,)
        )

        row = self._cursor.fetchone()
        return File.make_from(row)


    def update_path(self, source: str | Path, destination: str | Path) -> File:
        self._cursor.execute('''
            UPDATE files 
                SET path = ? WHERE path = ?
            RETURNING id, path, hash, created_at, last_updated
        ''', (str(destination), str(source)))
        row = self._cursor.fetchone()
        self.__connection.commit()

        file = File.make_from(row)

        return file


    def delete_file(self, path: str | Path) -> int:
        file = self.get_file_by_path(path)
        self._cursor.execute('''
            DELETE FROM files WHERE path = ?
        ''', (str(path),))
        self.__connection.commit()

        return file.id # type: ignore
     