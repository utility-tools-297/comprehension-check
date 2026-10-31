"""Markdown の穴メタ（メモ）と正誤回数の連動削除の単体テスト。"""

from pathlib import Path

from comprehension_check import attempts, db, mdmeta


def _conn(tmp_path: Path):  # type: ignore[no-untyped-def]
    return db.connect(tmp_path / "app.db")


def test_set_note_upsert_and_list(tmp_path: Path) -> None:
    """メモは upsert で設定でき、空でないものだけ一覧に出る。"""
    conn = _conn(tmp_path)
    try:
        mdmeta.set_note(conn, "doc1", 1, "覚える")
        mdmeta.set_note(conn, "doc1", 1, "やっぱり重要")  # 上書き
        mdmeta.set_note(conn, "doc1", 2, "")  # 空は一覧に出ない
        assert mdmeta.notes_for_doc(conn, "doc1") == {1: "やっぱり重要"}
    finally:
        conn.close()


def test_delete_for_cloze_clears_note_and_attempts(tmp_path: Path) -> None:
    """穴の削除でメモと正誤履歴の両方が消える。"""
    conn = _conn(tmp_path)
    try:
        mdmeta.set_note(conn, "doc1", 3, "memo")
        attempts.record_md(conn, "doc1", 3, "correct")
        assert attempts.counts_for_blank(conn, "doc1", attempts.md_blank_id(3)) == {
            "correct": 1,
            "incorrect": 0,
        }
        mdmeta.delete_for_cloze(conn, "doc1", 3)
        assert mdmeta.notes_for_doc(conn, "doc1") == {}
        assert attempts.counts_for_blank(conn, "doc1", attempts.md_blank_id(3)) == {
            "correct": 0,
            "incorrect": 0,
        }
    finally:
        conn.close()
