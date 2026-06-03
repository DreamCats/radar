from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def sqlite_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    path = tmp_path / "radar-config"
    path.mkdir()
    return path
