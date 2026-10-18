"""PDF/HTML の穴（Blank）の CRUD と重なり判定。

穴の矩形はページ内の正規化座標(0〜1・原点は左上)。テキスト選択は複数行で複数矩形、
矩形選択は1つ。初期仕様として、同一ページ内で既存の穴と重なる登録は拒否する。
"""

from __future__ import annotations

import json
import sqlite3

from comprehension_check import ids
from comprehension_check.models import Blank


def _row_to_blank(row: sqlite3.Row) -> Blank:
    """DB 行を Blank へ変換する。"""
    return Blank(
        id=row["id"],
        doc_id=row["doc_id"],
        page=row["page"],
        kind=row["kind"],
        rects=json.loads(row["rects"]),
        note=row["note"] if "note" in row.keys() else "",
        created_at=row["created_at"],
    )


def list_blanks(conn: sqlite3.Connection, doc_id: str) -> list[Blank]:
    """文書の穴を作成順に返す。"""
    rows = conn.execute(
        "SELECT * FROM blanks WHERE doc_id = ? ORDER BY created_at", (doc_id,)
    ).fetchall()
    return [_row_to_blank(r) for r in rows]


def _rect_overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    """2つの矩形が重なるか。"""
    return (
        a["x"] < b["x"] + b["w"]
        and b["x"] < a["x"] + a["w"]
        and a["y"] < b["y"] + b["h"]
        and b["y"] < a["y"] + a["h"]
    )


def _rects_overlap(ra: list[dict[str, float]], rb: list[dict[str, float]]) -> bool:
    """矩形リスト同士に重なりがあるか。"""
    return any(_rect_overlap(x, y) for x in ra for y in rb)


def add_blank(
    conn: sqlite3.Connection,
    doc_id: str,
    page: int,
    kind: str,
    rects: list[dict[str, float]],
) -> tuple[Blank | None, str]:
    """穴を登録する。同一ページで既存の穴と重なる場合は拒否。

    Returns:
        (登録された Blank, エラー文字列)。成功時はエラーが空文字。
    """
    rects = [r for r in rects if r.get("w", 0) > 0 and r.get("h", 0) > 0]
    if not rects:
        return None, "有効な範囲が選択されていません。"
    for existing in list_blanks(conn, doc_id):
        if existing.page == page and _rects_overlap(existing.rects, rects):
            return None, "既存の穴と重なる範囲には登録できません。"
    blank = Blank(
        id=ids.gen_id(),
        doc_id=doc_id,
        page=page,
        kind=kind,
        rects=rects,
        created_at=ids.now_string(),
    )
    conn.execute(
        "INSERT INTO blanks (id, doc_id, page, kind, rects, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (blank.id, blank.doc_id, blank.page, blank.kind, json.dumps(rects), blank.created_at),
    )
    conn.commit()
    return blank, ""


def delete_blank(conn: sqlite3.Connection, doc_id: str, blank_id: str) -> None:
    """穴を削除する。"""
    conn.execute("DELETE FROM blanks WHERE id = ? AND doc_id = ?", (blank_id, doc_id))
    conn.commit()


def set_note(conn: sqlite3.Connection, doc_id: str, blank_id: str, note: str) -> None:
    """穴のメモを更新する。"""
    conn.execute("UPDATE blanks SET note = ? WHERE id = ? AND doc_id = ?", (note, blank_id, doc_id))
    conn.commit()
