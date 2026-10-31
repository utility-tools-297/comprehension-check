"""一問一答（Q&A）セットの Markdown 生成・解析（往復パース）。

Q&A作問ツールが作る Markdown は次の体裁を正本とする（ファイルが唯一の正本＝二重管理しない）：

    <!-- cc:qa -->

    ## 問1

    問題文（改行・箇条書きなしの1行）

    {{c1::答え}}

- 先頭の ``MARKER`` でこのファイルが「Q&Aセット（ツールで編集できる）」だと自己識別する。
  描画時は ``strip_marker`` で取り除く（html:False のため残すと本文として見えてしまうので）。
- 表示の「問N」は並び順。``{{cK::}}`` の **K は固定の識別子**で、並べ替えても動かさない
  （正誤回数・メモが正しい問に付いて回るため。メタは (doc_id, K) をキーに別管理）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from comprehension_check import mdcloze

# ファイル先頭に置く自己識別マーカー。
MARKER = "<!-- cc:qa -->"

# 1項目（見出し行＋問題段落＋答えの穴）を取り出す。question は非貪欲で次の穴の直前まで。
_ITEM_RE = re.compile(r"^##[^\n]*\n+(.*?)\n+\{\{c(\d+)::(.*?)\}\}", re.MULTILINE | re.DOTALL)


@dataclass
class QAItem:
    """Q&Aセットの1項目。number は固定の識別子（並べ替えでも不変）。"""

    number: int
    question: str
    answer: str


def _sanitize(text: str) -> str:
    """問題文・答えを1行に正規化し、穴記法を壊す文字を無害化する。

    改行は空白へ（1行前提）。``{{``・``}}`` は穴の区切りと衝突するため分割して無害化する。
    """
    one_line = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
    return one_line.replace("{{", "{ {").replace("}}", "} }")


def is_qa(text: str) -> bool:
    """このテキストが Q&Aセット（先頭にマーカーがある）かどうか。"""
    return text.lstrip().startswith(MARKER)


def strip_marker(text: str) -> str:
    """描画用にマーカー行を取り除く（先頭の空行も詰める）。"""
    idx = text.find(MARKER)
    if idx == -1:
        return text
    return (text[:idx] + text[idx + len(MARKER) :]).lstrip("\n")


def render(items: list[QAItem]) -> str:
    """Q&A項目列を Markdown に書き出す（穴番号は保持、表示の問番号は並び順で振り直す）。"""
    parts: list[str] = [MARKER, ""]
    for pos, it in enumerate(items, start=1):
        parts.append(f"## 問{pos}")
        parts.append("")
        parts.append(_sanitize(it.question))
        parts.append("")
        parts.append(f"{{{{c{it.number}::{_sanitize(it.answer)}}}}}")
        parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n"


def generate(pairs: list[tuple[str, str]]) -> str:
    """新規作成：(問題, 答え) の列に c1..cN を採番して Markdown を作る。"""
    items = [QAItem(number=i, question=q, answer=a) for i, (q, a) in enumerate(pairs, start=1)]
    return render(items)


def parse(text: str) -> list[QAItem] | None:
    """Q&Aセットの Markdown を項目列へ復元する。非適合なら None（＝ツールでは編集できない）。"""
    if not is_qa(text):
        return None
    items = [
        QAItem(number=int(m.group(2)), question=m.group(1).strip(), answer=m.group(3).strip())
        for m in _ITEM_RE.finditer(text)
    ]
    if not items:
        return None
    # 見出しに対応しない穴（手書きで混ざった穴など）があれば、安全のため非適合扱いにする。
    if len(mdcloze.CLOZE_RE.findall(text)) != len(items):
        return None
    return items


def next_number(items: list[QAItem]) -> int:
    """次に割り当てる穴番号（既存の最大＋1）。削除済み番号は再利用しない。"""
    return max((it.number for it in items), default=0) + 1
