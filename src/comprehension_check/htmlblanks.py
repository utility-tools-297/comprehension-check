"""HTML の穴（HtmlBlank）の CRUD。

HTML はウィンドウ幅やフォントでリフローするため、PDF のようなページ内絶対座標では
穴が保持できない。そこで穴をアンカーで持つ:

- text: テキストアンカー {exact, prefix, suffix}。描画時に本文を再探索して span で包む。
- rect: 対象要素の CSS セレクタ＋要素内の正規化サブ矩形 {selector, x, y, w, h}。

アンカーの一致・重なり判定はサーバ側では DOM を持たないため、同一アンカーの重複登録だけを
拒否する（範囲の重なり抑止はクライアント側で DOM を見て行う。初期仕様）。
"""

from __future__ import annotations

import json
import sqlite3

from comprehension_check import ids
from comprehension_check.models import HtmlBlank

# HTML の穴は単一文書（ページ概念なし）。blanks.page には 0 を入れる。
_HTML_PAGE = 0


def _row_to_blank(row: sqlite3.Row) -> HtmlBlank:
    """DB 行を HtmlBlank へ変換する。"""
    return HtmlBlank(
        id=row["id"],
        doc_id=row["doc_id"],
        kind=row["kind"],
        payload=json.loads(row["payload"]) if row["payload"] else {},
        note=row["note"] if "note" in row.keys() else "",
        created_at=row["created_at"],
    )


def list_blanks(conn: sqlite3.Connection, doc_id: str) -> list[HtmlBlank]:
    """文書の穴を作成順に返す。"""
    rows = conn.execute(
        "SELECT * FROM blanks WHERE doc_id = ? ORDER BY created_at", (doc_id,)
    ).fetchall()
    return [_row_to_blank(r) for r in rows]


def add_blank(
    conn: sqlite3.Connection,
    doc_id: str,
    kind: str,
    payload: dict[str, object],
) -> tuple[HtmlBlank | None, str]:
    """穴を登録する。全く同じアンカーの重複だけを拒否する。

    Returns:
        (登録された HtmlBlank, エラー文字列)。成功時はエラーが空文字。
    """
    if kind not in ("text", "rect"):
        return None, "未知の穴種別です。"
    if kind == "text" and not str(payload.get("exact", "")).strip():
        return None, "有効な範囲が選択されていません。"
    if kind == "rect" and not str(payload.get("selector", "")).strip():
        return None, "対象要素が特定できませんでした。"
    for existing in list_blanks(conn, doc_id):
        if existing.kind == kind and existing.payload == payload:
            return None, "同じ箇所は既に穴になっています。"
    blank = HtmlBlank(
        id=ids.gen_id(),
        doc_id=doc_id,
        kind=kind,
        payload=payload,
        created_at=ids.now_string(),
    )
    conn.execute(
        "INSERT INTO blanks (id, doc_id, page, kind, rects, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            blank.id,
            blank.doc_id,
            _HTML_PAGE,
            blank.kind,
            "[]",
            json.dumps(payload),
            blank.created_at,
        ),
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
