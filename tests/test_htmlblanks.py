"""HTML 穴（HtmlBlank）の CRUD のテスト。"""

from pathlib import Path

from comprehension_check import db, htmlblanks


def _conn(tmp_path: Path):  # type: ignore[no-untyped-def]
    """一時 DB 接続。"""
    return db.connect(tmp_path / "app.db")


def test_add_text_and_list(tmp_path: Path) -> None:
    """テキストアンカーの穴を登録・取得できる。"""
    conn = _conn(tmp_path)
    payload = {"exact": "需要と供給", "prefix": "価格は", "suffix": "で決まる"}
    blank, error = htmlblanks.add_blank(conn, "doc1", "text", payload)
    assert error == ""
    assert blank is not None
    got = htmlblanks.list_blanks(conn, "doc1")
    assert len(got) == 1
    assert got[0].kind == "text"
    assert got[0].payload == payload


def test_add_rect(tmp_path: Path) -> None:
    """矩形（要素基準）の穴を登録できる。"""
    conn = _conn(tmp_path)
    payload = {"selector": "body > div > img", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.4}
    blank, error = htmlblanks.add_blank(conn, "doc1", "rect", payload)
    assert error == ""
    assert blank is not None


def test_duplicate_rejected(tmp_path: Path) -> None:
    """全く同じアンカーの重複は拒否。"""
    conn = _conn(tmp_path)
    payload = {"exact": "東京", "prefix": "首都は", "suffix": "である"}
    htmlblanks.add_blank(conn, "doc1", "text", payload)
    _, error = htmlblanks.add_blank(conn, "doc1", "text", dict(payload))
    assert error != ""
    assert len(htmlblanks.list_blanks(conn, "doc1")) == 1


def test_empty_text_rejected(tmp_path: Path) -> None:
    """空のテキストアンカーは拒否。"""
    conn = _conn(tmp_path)
    _, error = htmlblanks.add_blank(
        conn, "doc1", "text", {"exact": "  ", "prefix": "", "suffix": ""}
    )
    assert error != ""


def test_unknown_kind_rejected(tmp_path: Path) -> None:
    """未知の種別は拒否。"""
    conn = _conn(tmp_path)
    _, error = htmlblanks.add_blank(conn, "doc1", "polygon", {"exact": "x"})
    assert error != ""


def test_delete(tmp_path: Path) -> None:
    """穴を削除できる。"""
    conn = _conn(tmp_path)
    blank, _ = htmlblanks.add_blank(
        conn, "doc1", "text", {"exact": "語", "prefix": "", "suffix": ""}
    )
    assert blank is not None
    htmlblanks.delete_blank(conn, "doc1", blank.id)
    assert htmlblanks.list_blanks(conn, "doc1") == []
