"""文書レジストリの CRUD（SQLite の documents テーブル）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from comprehension_check import ids
from comprehension_check.models import Document


def _row_to_document(row: sqlite3.Row) -> Document:
    """DB 行を Document へ変換する。"""
    return Document(
        id=row["id"],
        title=row["title"],
        doc_type=row["doc_type"],
        path=row["path"],
        created_at=row["created_at"],
    )


def add_document(conn: sqlite3.Connection, title: str, doc_type: str, path: str) -> Document:
    """文書を登録して Document を返す。title 省略時は呼び出し側でファイル名を入れる。"""
    doc = Document(
        id=ids.gen_id(),
        title=title or Path(path).stem,
        doc_type=doc_type,
        path=path,
        created_at=ids.now_string(),
    )
    conn.execute(
        "INSERT INTO documents (id, title, doc_type, path, created_at) VALUES (?, ?, ?, ?, ?)",
        (doc.id, doc.title, doc.doc_type, doc.path, doc.created_at),
    )
    conn.commit()
    return doc


def list_documents(conn: sqlite3.Connection) -> list[Document]:
    """登録済み文書を新しい順に返す。"""
    rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [_row_to_document(r) for r in rows]


def get_document(conn: sqlite3.Connection, doc_id: str) -> Document | None:
    """ID で文書を取得する（無ければ None）。"""
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return _row_to_document(row) if row else None


def delete_document(conn: sqlite3.Connection, doc_id: str) -> None:
    """登録を削除する（元ファイルは消さない）。"""
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
