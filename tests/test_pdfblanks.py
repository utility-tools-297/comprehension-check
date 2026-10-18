"""PDF 穴（Blank）の CRUD と重なり判定のテスト。"""

from pathlib import Path

from comprehension_check import db, pdfblanks


def _conn(tmp_path: Path):  # type: ignore[no-untyped-def]
    """一時 DB 接続。"""
    return db.connect(tmp_path / "app.db")


def _rect(x: float, y: float, w: float, h: float) -> dict[str, float]:
    return {"x": x, "y": y, "w": w, "h": h}


def test_add_and_list(tmp_path: Path) -> None:
    """登録した穴が取得できる。"""
    conn = _conn(tmp_path)
    blank, error = pdfblanks.add_blank(conn, "doc1", 1, "text", [_rect(0.1, 0.1, 0.2, 0.05)])
    assert error == ""
    assert blank is not None
    got = pdfblanks.list_blanks(conn, "doc1")
    assert len(got) == 1
    assert got[0].kind == "text"
    assert got[0].page == 1


def test_overlap_rejected(tmp_path: Path) -> None:
    """同一ページで重なる穴は拒否。"""
    conn = _conn(tmp_path)
    pdfblanks.add_blank(conn, "doc1", 1, "rect", [_rect(0.1, 0.1, 0.2, 0.2)])
    _, error = pdfblanks.add_blank(conn, "doc1", 1, "rect", [_rect(0.2, 0.2, 0.2, 0.2)])
    assert error != ""
    assert len(pdfblanks.list_blanks(conn, "doc1")) == 1


def test_non_overlap_allowed(tmp_path: Path) -> None:
    """離れた位置・別ページは登録できる。"""
    conn = _conn(tmp_path)
    pdfblanks.add_blank(conn, "doc1", 1, "rect", [_rect(0.1, 0.1, 0.1, 0.1)])
    _, e1 = pdfblanks.add_blank(conn, "doc1", 1, "rect", [_rect(0.5, 0.5, 0.1, 0.1)])
    _, e2 = pdfblanks.add_blank(conn, "doc1", 2, "rect", [_rect(0.1, 0.1, 0.1, 0.1)])
    assert e1 == "" and e2 == ""
    assert len(pdfblanks.list_blanks(conn, "doc1")) == 3


def test_empty_rects_rejected(tmp_path: Path) -> None:
    """面積のない矩形は拒否。"""
    conn = _conn(tmp_path)
    _, error = pdfblanks.add_blank(conn, "doc1", 1, "rect", [_rect(0.1, 0.1, 0.0, 0.0)])
    assert error != ""


def test_delete(tmp_path: Path) -> None:
    """穴を削除できる。"""
    conn = _conn(tmp_path)
    blank, _ = pdfblanks.add_blank(conn, "doc1", 1, "text", [_rect(0.1, 0.1, 0.2, 0.05)])
    assert blank is not None
    pdfblanks.delete_blank(conn, "doc1", blank.id)
    assert pdfblanks.list_blanks(conn, "doc1") == []
