"""Markdown クローズ処理のテスト。"""

from comprehension_check import mdcloze


def test_render_cloze_to_span() -> None:
    """記法がマスク用 span に変換される。"""
    html = mdcloze.render_html("日本の首都は{{c1::東京都}}である。")
    assert 'class="cloze"' in html
    assert 'data-cloze="1"' in html
    assert "東京都" in html


def test_render_block_has_line_attrs() -> None:
    """ブロック要素に元ソース行が付与される。"""
    html = mdcloze.render_html("# 見出し\n\n本文です。")
    assert "data-ls=" in html
    assert "data-le=" in html


def test_list_and_next_number() -> None:
    """穴の一覧と次番号が取れる。"""
    text = "{{c1::A}}と{{c3::B}}"
    clozes = mdcloze.list_clozes(text)
    assert [c.number for c in clozes] == [1, 3]
    assert mdcloze.next_number(text) == 4
    assert mdcloze.next_number("穴なし") == 1


def test_insert_cloze_basic() -> None:
    """選択語に記法が挿入される。"""
    text = "日本の首都は東京都である。"
    new_text, error = mdcloze.insert_cloze(text, 0, 1, "東京都", 0)
    assert error == ""
    assert new_text == "日本の首都は{{c1::東京都}}である。"


def test_insert_overlap_rejected() -> None:
    """既存の穴と重なる選択は拒否される。"""
    text = "日本の首都は{{c1::東京都}}である。"
    # 既存クローズの中身 "東京都" を再度選ぼうとすると重なりで不可
    _, error = mdcloze.insert_cloze(text, 0, 1, "東京都", 0)
    assert error != ""


def test_insert_occurrence_picks_nth() -> None:
    """同一ブロック内の重複語は出現番目で選べる。"""
    text = "りんごとりんごを食べた。"
    new_text, error = mdcloze.insert_cloze(text, 0, 1, "りんご", 1)
    assert error == ""
    assert new_text == "りんごと{{c1::りんご}}を食べた。"


def test_insert_not_found() -> None:
    """選択語が元ファイルに無ければエラー。"""
    _, error = mdcloze.insert_cloze("あいうえお", 0, 1, "かきくけこ", 0)
    assert error != ""


def test_remove_cloze() -> None:
    """指定番号の穴を外して中身を残す。"""
    text = "{{c1::A}}と{{c2::B}}"
    assert mdcloze.remove_cloze(text, 1) == "Aと{{c2::B}}"
