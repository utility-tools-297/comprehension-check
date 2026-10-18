"""穴ごとの正誤記録（いつ正解/不正解したかの履歴）と集計。

実践で穴を解いたときに正解/不正解を記録する。履歴は timestamp 付きで残し、
画面にはその集計（正解数・不正解数）を表示する。PDF・HTML いずれの穴も
blanks.id をキーに同じ attempts テーブルで扱う。
"""

from __future__ import annotations

import sqlite3

from comprehension_check import ids

# 記録できる結果種別。
RESULTS = ("correct", "incorrect")


def record(
    conn: sqlite3.Connection, doc_id: str, blank_id: str, result: str
) -> tuple[dict[str, int] | None, str]:
    """正誤を1件記録し、その穴の最新集計を返す。

    Returns:
        (集計 {correct, incorrect}, エラー文字列)。成功時はエラーが空文字。
    """
    if result not in RESULTS:
        return None, "不正な結果種別です。"
    # 対象の穴が存在することを確認（存在しない blank への記録を防ぐ）。
    row = conn.execute(
        "SELECT 1 FROM blanks WHERE id = ? AND doc_id = ?", (blank_id, doc_id)
    ).fetchone()
    if row is None:
        return None, "対象の穴が見つかりません。"
    conn.execute(
        "INSERT INTO attempts (doc_id, blank_id, result, created_at) VALUES (?, ?, ?, ?)",
        (doc_id, blank_id, result, ids.now_string()),
    )
    conn.commit()
    return counts_for_blank(conn, doc_id, blank_id), ""


def counts_for_blank(conn: sqlite3.Connection, doc_id: str, blank_id: str) -> dict[str, int]:
    """1つの穴の正解数・不正解数を返す。"""
    rows = conn.execute(
        "SELECT result, COUNT(*) AS n FROM attempts "
        "WHERE doc_id = ? AND blank_id = ? GROUP BY result",
        (doc_id, blank_id),
    ).fetchall()
    out = {"correct": 0, "incorrect": 0}
    for r in rows:
        if r["result"] in out:
            out[r["result"]] = int(r["n"])
    return out


def counts_for_doc(conn: sqlite3.Connection, doc_id: str) -> dict[str, dict[str, int]]:
    """文書内の全ての穴について {blank_id: {correct, incorrect}} を返す。"""
    rows = conn.execute(
        "SELECT blank_id, result, COUNT(*) AS n FROM attempts "
        "WHERE doc_id = ? GROUP BY blank_id, result",
        (doc_id,),
    ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        counts = out.setdefault(r["blank_id"], {"correct": 0, "incorrect": 0})
        if r["result"] in counts:
            counts[r["result"]] = int(r["n"])
    return out


def delete_for_blank(conn: sqlite3.Connection, doc_id: str, blank_id: str) -> None:
    """穴の削除に伴い、その正誤履歴も消す。"""
    conn.execute("DELETE FROM attempts WHERE doc_id = ? AND blank_id = ?", (doc_id, blank_id))
    conn.commit()
