"""Q&Aセットの生成・解析（往復パース）の単体テスト。"""

from comprehension_check import qaset


def test_generate_is_qa_and_parse_roundtrip() -> None:
    """生成した Markdown は Q&Aセットと判定でき、解析で元の問題・答えに戻る。"""
    text = qaset.generate([("日本の首都は？", "東京"), ("最大の湖は？", "琵琶湖")])
    assert qaset.is_qa(text)
    assert text.startswith(qaset.MARKER)
    assert "## 問1" in text and "## 問2" in text
    assert "{{c1::東京}}" in text and "{{c2::琵琶湖}}" in text

    items = qaset.parse(text)
    assert items is not None
    assert [(it.number, it.question, it.answer) for it in items] == [
        (1, "日本の首都は？", "東京"),
        (2, "最大の湖は？", "琵琶湖"),
    ]


def test_reorder_keeps_cloze_numbers() -> None:
    """並べ替えても各項目の穴番号は不変（表示の問番号だけ入れ替わる）。"""
    items = qaset.parse(qaset.generate([("Q1", "A1"), ("Q2", "A2")]))
    assert items is not None
    reordered = [items[1], items[0]]  # 入れ替え
    text = qaset.render(reordered)
    # 表示は 問1=元の2番目、問2=元の1番目。穴番号は保持。
    assert text.index("{{c2::A2}}") < text.index("{{c1::A1}}")
    again = qaset.parse(text)
    assert again is not None
    assert [(it.number, it.answer) for it in again] == [(2, "A2"), (1, "A1")]


def test_render_keeps_nonsequential_numbers_and_renumbers_display() -> None:
    """穴番号が連番でなくても保持し、表示の問番号は並び順で振り直す。"""
    text = qaset.render([qaset.QAItem(5, "q5", "a5"), qaset.QAItem(2, "q2", "a2")])
    assert "## 問1" in text and "## 問2" in text
    assert "{{c5::a5}}" in text and "{{c2::a2}}" in text
    assert qaset.next_number(qaset.parse(text) or []) == 6


def test_sanitize_normalizes_newlines_and_escapes_braces() -> None:
    """改行は空白へ、穴記法を壊す `{{`・`}}` は無害化される。"""
    text = qaset.generate([("複数\n行の問題", "答え}}に{{記号")])
    items = qaset.parse(text)
    assert items is not None
    assert items[0].question == "複数 行の問題"
    assert items[0].answer == "答え} }に{ {記号"


def test_non_qa_text_is_not_parsed() -> None:
    """マーカーの無い通常 Markdown は Q&Aセットと見なさない。"""
    assert qaset.is_qa("## 問1\n\n本文\n\n{{c1::答え}}") is False
    assert qaset.parse("## ふつうの見出し\n\n本文です。") is None


def test_strip_marker_removes_marker_line() -> None:
    """描画用にマーカーを取り除く（先頭の空行も詰める）。"""
    text = qaset.generate([("Q", "A")])
    stripped = qaset.strip_marker(text)
    assert qaset.MARKER not in stripped
    assert stripped.startswith("## 問1")
