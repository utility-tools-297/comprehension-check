"""Markdown の穴埋め（クローズ）処理。

穴の正本は元 Markdown ファイル内の記法 ``{{cN::answer}}``（N は識別用の番号）。
- 描画: Markdown→HTML に変換し、各ブロック要素へ元ソース行(data-ls/data-le)を付与、
  さらに記法をマスク用の ``<span class="cloze">`` に変換する。
- 作成: 元ソースの指定位置へ記法を挿入（既存の穴と重なる範囲は不可）。
- 削除: 指定番号の記法を外し、中身の文字列だけ残す。

アプリ上の選択→書き戻しは「ブロックの元ソース行範囲＋選択文字列＋ブロック内の出現番目」で
位置を特定する。装飾記法や既存クローズが絡む重複選択では位置がずれ得る（MVP の既知の制約）。
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

from comprehension_check.models import Cloze

# {{cN::answer}} 記法。answer は改行を含み得る（非貪欲で最初の }} まで）。
CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)\}\}", re.DOTALL)


def _md() -> MarkdownIt:
    """素の HTML を通さない CommonMark レンダラ。"""
    return MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})


def _clozes_to_spans(html: str) -> str:
    """描画後 HTML 中の記法をマスク用 span へ置換する。"""

    def repl(m: re.Match[str]) -> str:
        num, answer = m.group(1), m.group(2)
        return f'<span class="cloze" data-cloze="{num}" role="button" tabindex="0">{answer}</span>'

    return CLOZE_RE.sub(repl, html)


def render_html(md_text: str) -> str:
    """Markdown を、ブロック行情報とクローズ span を含む HTML に変換する。"""
    md = _md()
    tokens = md.parse(md_text)
    for tok in tokens:
        # 元ソース行を持つブロック（開きタグ・自己完結タグ）に行範囲を付ける
        if tok.map and tok.nesting >= 0:
            tok.attrSet("data-ls", str(tok.map[0]))
            tok.attrSet("data-le", str(tok.map[1]))
    html: str = md.renderer.render(tokens, md.options, {})
    return _clozes_to_spans(html)


def list_clozes(md_text: str) -> list[Cloze]:
    """元ソースに含まれる穴の一覧（出現順）。"""
    return [Cloze(number=int(m.group(1)), answer=m.group(2)) for m in CLOZE_RE.finditer(md_text)]


def next_number(md_text: str) -> int:
    """次に割り当てるクローズ番号（既存の最大＋1、無ければ1）。"""
    nums = [int(m.group(1)) for m in CLOZE_RE.finditer(md_text)]
    return (max(nums) + 1) if nums else 1


def _line_offsets(text: str) -> list[int]:
    """各行の開始文字オフセット（offsets[n] = n 行目の先頭位置）。"""
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def insert_cloze(
    md_text: str, line_start: int, line_end: int, selected: str, occurrence: int
) -> tuple[str, str]:
    """選択範囲へクローズ記法を挿入した新テキストを返す。

    Args:
        md_text: 元 Markdown 全文。
        line_start: 対象ブロックの開始行（0始まり）。
        line_end: 対象ブロックの終了行（排他）。
        selected: 選択された文字列。
        occurrence: ブロック内での選択文字列の出現番目（0始まり）。

    Returns:
        (新テキスト, エラー文字列)。成功時はエラーが空文字。
    """
    if not selected.strip():
        return md_text, "選択が空です。"
    offsets = _line_offsets(md_text)
    n = len(offsets)
    if line_start < 0 or line_start >= n:
        return md_text, "対象ブロックを特定できませんでした。"
    block_start = offsets[line_start]
    block_end = offsets[line_end] if line_end < n else len(md_text)
    block = md_text[block_start:block_end]

    # ブロック内の selected の全出現位置（絶対オフセット）
    matches: list[int] = []
    pos = block.find(selected)
    while pos != -1:
        matches.append(block_start + pos)
        pos = block.find(selected, pos + 1)
    if not matches:
        return md_text, "選択テキストが元ファイル内に見つかりませんでした。"

    abs_pos = matches[occurrence] if 0 <= occurrence < len(matches) else matches[0]
    end_pos = abs_pos + len(selected)

    # 既存の穴と重なる範囲は不可（初期仕様）
    existing = [(m.start(), m.end()) for m in CLOZE_RE.finditer(md_text)]
    if any(abs_pos < e and s < end_pos for s, e in existing):
        return md_text, "既存の穴と重なる範囲には登録できません。"

    num = next_number(md_text)
    new_text = f"{md_text[:abs_pos]}{{{{c{num}::{selected}}}}}{md_text[end_pos:]}"
    return new_text, ""


def remove_cloze(md_text: str, number: int) -> str:
    """指定番号の穴を外し、中身の文字列だけ残した新テキストを返す。"""

    def repl(m: re.Match[str]) -> str:
        return m.group(2) if int(m.group(1)) == number else m.group(0)

    return CLOZE_RE.sub(repl, md_text)
