"""SQLite 接続とスキーマ初期化。

- documents: 文書レジストリ（全形式共通）。
- blanks: PDF/HTML の穴（元ファイルを変えない形式はアプリ側で管理する）。
  PDF は矩形「ページ内の正規化座標(0〜1)」のリストを rects(JSON) に持つ。
  HTML はリフローするため座標でなく、テキストアンカーや要素基準の情報を payload(JSON) に持つ。
  Markdown の穴は元ファイルの記法が正本なので DB には持たない。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    doc_type   TEXT NOT NULL,
    path       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blanks (
    id         TEXT PRIMARY KEY,
    doc_id     TEXT NOT NULL,
    page       INTEGER NOT NULL,
    kind       TEXT NOT NULL,
    rects      TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blanks_doc ON blanks (doc_id, page);

-- 穴ごとの正誤記録（いつ正解/不正解したかの履歴）。集計して画面に数を出す。
CREATE TABLE IF NOT EXISTS attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     TEXT NOT NULL,
    blank_id   TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_blank ON attempts (doc_id, blank_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """既存 DB を現行スキーマへ寄せる（不足列の追加）。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(blanks)").fetchall()}
    if "payload" not in cols:
        conn.execute("ALTER TABLE blanks ADD COLUMN payload TEXT NOT NULL DEFAULT ''")
    if "note" not in cols:
        conn.execute("ALTER TABLE blanks ADD COLUMN note TEXT NOT NULL DEFAULT ''")


def connect(db_path: Path) -> sqlite3.Connection:
    """DB へ接続し、必要なら親フォルダとスキーマを用意して返す。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn
