"""データモデル。

- Document: 文書レジストリ（全形式共通）。
- Cloze: Markdown の穴（元ファイルの記法が正本）。
- Blank: PDF/HTML の穴（アプリ側 DB 管理。ページ内の正規化矩形のリストを持つ）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 対応文書種別
DOC_MARKDOWN = "markdown"
DOC_PDF = "pdf"
DOC_HTML = "html"


@dataclass
class Document:
    """登録された元文書1件。元ファイルはユーザー任意フォルダに置かれ、path で参照する。"""

    id: str
    title: str
    doc_type: str
    path: str
    created_at: str


@dataclass
class Cloze:
    """Markdown 文書内の1つの穴（元ファイルの記法 {{cN::answer}} に対応）。"""

    number: int
    answer: str


# 穴の種別（PDF/HTML）
BLANK_TEXT = "text"
BLANK_RECT = "rect"


@dataclass
class Blank:
    """PDF 文書内の1つの穴（ページ固定レイアウト向け）。

    rects はページ内の正規化座標(0〜1・原点は左上)の矩形リスト。テキスト選択は複数行で
    複数矩形になり得る。矩形選択は1つ。クリックで一括して表示/非表示される。
    """

    id: str
    doc_id: str
    page: int
    kind: str
    rects: list[dict[str, float]] = field(default_factory=list)
    note: str = ""
    created_at: str = ""


@dataclass
class HtmlBlank:
    """HTML 文書内の1つの穴（リフローするため座標でなくアンカーで持つ）。

    kind=text: payload に {exact, prefix, suffix}（テキストアンカー）。描画時に本文を
        再探索して該当範囲を span で包む。
    kind=rect: payload に {selector, x, y, w, h}（対象要素の CSS セレクタ＋要素内の
        正規化サブ矩形）。描画時に要素を見つけ、その矩形上にマスクを重ねる。
    """

    id: str
    doc_id: str
    kind: str
    payload: dict[str, object] = field(default_factory=dict)
    note: str = ""
    created_at: str = ""
