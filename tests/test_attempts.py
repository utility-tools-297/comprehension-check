"""正誤記録（attempts）の単体テスト。"""

from pathlib import Path

from comprehension_check import attempts, db, pdfblanks


def _conn(tmp_path: Path):  # type: ignore[no-untyped-def]
    return db.connect(tmp_path / "app.db")


def test_record_and_counts(tmp_path: Path) -> None:
    """正解/不正解を記録し、集計が増えること。"""
    conn = _conn(tmp_path)
    try:
        blank, err = pdfblanks.add_blank(
            conn, "doc1", 1, "rect", [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}]
        )
        assert err == "" and blank is not None

        counts, err = attempts.record(conn, "doc1", blank.id, "correct")
        assert err == "" and counts == {"correct": 1, "incorrect": 0}
        attempts.record(conn, "doc1", blank.id, "correct")
        counts, _ = attempts.record(conn, "doc1", blank.id, "incorrect")
        assert counts == {"correct": 2, "incorrect": 1}

        assert attempts.counts_for_blank(conn, "doc1", blank.id) == {"correct": 2, "incorrect": 1}
        assert attempts.counts_for_doc(conn, "doc1") == {blank.id: {"correct": 2, "incorrect": 1}}
    finally:
        conn.close()


def test_record_rejects_unknown_result_and_missing_blank(tmp_path: Path) -> None:
    """不正な結果種別・存在しない穴は拒否される。"""
    conn = _conn(tmp_path)
    try:
        counts, err = attempts.record(conn, "doc1", "nope", "correct")
        assert counts is None and err  # 穴が無い

        blank, _ = pdfblanks.add_blank(
            conn, "doc1", 1, "rect", [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}]
        )
        assert blank is not None
        counts, err = attempts.record(conn, "doc1", blank.id, "maybe")
        assert counts is None and err  # 種別が不正
    finally:
        conn.close()


def test_delete_for_blank_clears_history(tmp_path: Path) -> None:
    """穴の削除に伴い履歴も消える。"""
    conn = _conn(tmp_path)
    try:
        blank, _ = pdfblanks.add_blank(
            conn, "doc1", 1, "rect", [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}]
        )
        assert blank is not None
        attempts.record(conn, "doc1", blank.id, "correct")
        attempts.delete_for_blank(conn, "doc1", blank.id)
        assert attempts.counts_for_blank(conn, "doc1", blank.id) == {"correct": 0, "incorrect": 0}
    finally:
        conn.close()
