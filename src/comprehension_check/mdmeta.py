"""Markdown の穴のメタ（メモ）の CRUD（SQLite の md_cloze_meta テーブル）。

Markdown の穴の「内容」は元ファイルの記法 ``{{cN::answer}}`` が正本。ここでは二重管理を避けるため
**メモだけ**を ``(doc_id, 穴番号)`` をキーに持つ。正解/不正解の回数は attempts テーブル側で
``blank_id="md-<番号>"`` として扱う（PDF/HTML と同じ仕組み）。
"""

from __future__ import annotations

import sqlite3

from comprehension_check import attempts


def set_note(conn: sqlite3.Connection, doc_id: str, number: int, note: str) -> None:
    """穴のメモを設定する（無ければ作る・あれば更新する）。"""
    conn.execute(
        "INSERT INTO md_cloze_meta (doc_id, number, note) VALUES (?, ?, ?) "
        "ON CONFLICT(doc_id, number) DO UPDATE SET note = excluded.note",
        (doc_id, number, note),
    )
    conn.commit()


def notes_for_doc(conn: sqlite3.Connection, doc_id: str) -> dict[int, str]:
    """文書内の穴番号→メモの辞書（メモが空でない穴だけ）。"""
    rows = conn.execute(
        "SELECT number, note FROM md_cloze_meta WHERE doc_id = ? AND note != ''", (doc_id,)
    ).fetchall()
    return {int(r["number"]): str(r["note"]) for r in rows}


def delete_for_cloze(conn: sqlite3.Connection, doc_id: str, number: int) -> None:
    """穴の削除に伴い、その穴のメモと正誤履歴を消す。"""
    conn.execute("DELETE FROM md_cloze_meta WHERE doc_id = ? AND number = ?", (doc_id, number))
    conn.commit()
    attempts.delete_for_blank(conn, doc_id, attempts.md_blank_id(number))
