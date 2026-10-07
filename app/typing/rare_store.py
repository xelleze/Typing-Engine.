"""Sparse adaptive familiarity; common words never enter the database."""
from pathlib import Path
import sqlite3
from time import time
import unicodedata


class RareWordStore:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.execute('''CREATE TABLE IF NOT EXISTS rare_words (
            word TEXT PRIMARY KEY,
            zipf REAL,
            seen_count INTEGER,
            last_seen INTEGER
        )''')
        self.connection.commit()

    @staticmethod
    def normalize(word: str) -> str:
        return unicodedata.normalize('NFC', word.lower())

    def seen_count(self, word: str) -> int:
        row = self.connection.execute('SELECT seen_count FROM rare_words WHERE word = ?',
                                      (self.normalize(word),)).fetchone()
        return row[0] if row else 0

    def record(self, word: str, zipf: float) -> None:
        if zipf >= 3.5:
            return
        with self.connection:
            self.connection.execute('''INSERT INTO rare_words (word, zipf, seen_count, last_seen)
                VALUES (?, ?, 1, ?) ON CONFLICT(word) DO UPDATE SET
                zipf = excluded.zipf, seen_count = rare_words.seen_count + 1,
                last_seen = excluded.last_seen''', (self.normalize(word), zipf, int(time())))

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
