"""Shared SQLite access for the Campus Customs backend."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / 'data'
# Overridable for testing (e.g. pointing at a scratch copy, or a missing file to test error handling).
DB_PATH = Path(os.getenv('CAMPUS_CUSTOMS_DB', str(DATA_DIR / 'campus_customs.db')))


@contextmanager
def get_connection(*, write: bool = False) -> Iterator[sqlite3.Connection]:
    """Open the database read-only by default.

    Only account creation and saved chat history open a writable connection (write=True);
    catalogue and inventory code never does.
    Writes are committed when the block exits cleanly and rolled back on error.
    """
    mode = 'rw' if write else 'ro'
    conn = sqlite3.connect(f'file:{DB_PATH}?mode={mode}', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if write:
            conn.commit()
    except Exception:
        if write:
            conn.rollback()
        raise
    finally:
        conn.close()
