"""HTTP ルート（文書一覧・登録・ビューア・穴の操作）。

- Markdown: 穴は元ファイルの記法が正本（cloze API）。
- PDF: 元ファイルは不変。穴は DB 管理（blanks API）。元 PDF は raw で配信し PDF.js が描画する。
- HTML: 元ファイルは不変。穴は DB 管理（html-blanks API）。元 HTML と同じ階層の資材を asset
  で同一オリジン配信し、iframe に表示する（リフローするためアンカーで穴を保持）。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from comprehension_check import attempts, db, htmlblanks, mdcloze, pdfblanks, store
from comprehension_check.config import Config
from comprehension_check.models import DOC_HTML, DOC_MARKDOWN, DOC_PDF, Document

logger = logging.getLogger(__name__)

# 拡張子 → 文書種別
_TYPE_BY_SUFFIX = {
    ".md": DOC_MARKDOWN,
    ".markdown": DOC_MARKDOWN,
    ".pdf": DOC_PDF,
    ".html": DOC_HTML,
    ".htm": DOC_HTML,
}


def _clean_path_input(raw: str) -> str:
    """フォームに貼られたパス文字列を実パスへ正規化する（引用符・file URL 等を吸収）。"""
    s = raw.strip().strip('"').strip("'").strip()
    # ブラウザのアドレスバー等からの file:// URL 貼り付けに対応。
    if s.lower().startswith("file:"):
        parsed = urlparse(s)
        s = unquote(parsed.path)
        # Windows の "/C:/..." を "C:/..." へ。
        if len(s) >= 3 and s[0] == "/" and s[2] == ":":
            s = s[1:]
    # ~ と環境変数を展開。
    return os.path.expandvars(os.path.expanduser(s))


def _resolve_input_path(raw: str) -> Path | None:
    """入力パスを解決して実在ファイルを返す（Unicode 正規化ゆらぎも吸収）。無ければ None。"""
    s = _clean_path_input(raw)
    if not s:
        return None
    p = Path(s)
    if p.is_file():
        return p
    # 保存名の NFC/NFD 差などで一致しない場合に備え、正規化を試す。
    for form in ("NFC", "NFD"):
        q = Path(unicodedata.normalize(form, s))
        if q.is_file():
            return q
    # 親フォルダ内に、正規化すれば一致するファイルがあれば採用（名前のゆらぎ吸収）。
    try:
        target = unicodedata.normalize("NFC", p.name)
        if p.parent.is_dir():
            for entry in p.parent.iterdir():
                if entry.is_file() and unicodedata.normalize("NFC", entry.name) == target:
                    return entry
    except OSError:
        pass
    return None


def _diagnose_path(raw: str) -> str:
    """登録に失敗したパスを画面で自己診断できる説明文を作る。"""
    s = _clean_path_input(raw)
    if not s:
        return "指定したパスにファイルが見つかりませんでした。パスが空です。"
    parts = [f"指定したパスにファイルが見つかりませんでした。試したパス: {s}"]
    p = Path(s)
    parent = p.parent
    if not parent.exists():
        parts.append("※ 指定フォルダ自体が存在しません（パスの打ち間違い・ドライブ違いの可能性）。")
    elif not parent.is_dir():
        parts.append("※ 親がフォルダではありません。")
    else:
        try:
            cands = [
                e.name
                for e in parent.iterdir()
                if e.is_file() and e.suffix.lower() in _TYPE_BY_SUFFIX
            ]
        except OSError:
            cands = []
        if cands:
            shown = " / ".join(cands[:8])
            parts.append(f"このフォルダにある登録可能ファイル: {shown}")
        else:
            parts.append(
                "※ このフォルダに登録可能な拡張子（.md/.pdf/.html 等）のファイルがありません。"
            )
    return "  ".join(parts)


# ネイティブのファイル選択ダイアログ（OS の「開く」）を開く子プロセス用コード。
# 本体プロセスで tkinter を動かすと uvicorn と相性が悪いため、別プロセスで開いて
# 選択された絶対パスだけを UTF-8 で標準出力へ返す。
_PICK_DIALOG_CODE = (
    "import tkinter as tk, sys\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "types = [('対応文書', '*.md *.markdown *.pdf *.html *.htm'), ('すべて', '*.*')]\n"
    "p = filedialog.askopenfilename(title='文書を選択', filetypes=types)\n"
    "sys.stdout.buffer.write((p or '').encode('utf-8'))\n"
)


def _pick_file_dialog() -> str:
    """OS のファイル選択ダイアログを開き、選ばれた絶対パスを返す（キャンセル時は空）。"""
    try:
        done = subprocess.run(
            [sys.executable, "-c", _PICK_DIALOG_CODE],
            capture_output=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", "replace").strip()


def _read_text(path: str) -> str | None:
    """UTF-8 でファイルを読む（無ければ None）。"""
    p = Path(path)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8")


def _write_text(path: str, text: str) -> None:
    """UTF-8 でファイルを書く。"""
    Path(path).write_text(text, encoding="utf-8")


def _resolve_asset(doc_path: str, rel: str) -> Path | None:
    """文書と同階層の資材パスを安全に解決する（親への遡上を防ぐ）。

    Returns:
        配信してよい実ファイルのパス。範囲外・非ファイルなら None。
    """
    base = Path(doc_path).resolve().parent
    try:
        target = (base / rel).resolve()
    except (OSError, ValueError):
        return None
    if target != base and base not in target.parents:
        return None
    if not target.is_file():
        return None
    return target


def build_router(config: Config, templates: Jinja2Templates) -> APIRouter:
    """設定とテンプレートを束ねたルータを返す。"""
    router = APIRouter()

    def _get_doc(doc_id: str) -> Document | None:
        conn = db.connect(config.db_path)
        try:
            return store.get_document(conn, doc_id)
        finally:
            conn.close()

    def _render_index(request: Request, err: str = "", err_msg: str = "") -> Response:
        conn = db.connect(config.db_path)
        try:
            docs = store.list_documents(conn)
        finally:
            conn.close()
        # 各文書の元ファイルが現存するか（一覧で警告表示するため）
        missing = {d.id for d in docs if not Path(d.path).is_file()}
        return templates.TemplateResponse(
            request,
            "index.html",
            {"docs": docs, "missing": missing, "err": err, "err_msg": err_msg},
        )

    @router.get("/")
    def index(request: Request, err: str = "") -> Response:
        return _render_index(request, err=err)

    @router.post("/documents")
    def add_document(request: Request, path: str = Form(...), title: str = Form("")) -> Response:
        p = _resolve_input_path(path)
        if p is None:
            # どのパスを試したか・フォルダ内の実ファイル名を見せて自己診断できるようにする。
            logger.warning(
                "document register failed: raw=%r cleaned=%r", path, _clean_path_input(path)
            )
            return _render_index(request, err_msg=_diagnose_path(path))
        doc_type = _TYPE_BY_SUFFIX.get(p.suffix.lower())
        if doc_type is None:
            return RedirectResponse("/?err=type", status_code=303)
        conn = db.connect(config.db_path)
        try:
            store.add_document(conn, title.strip(), doc_type, str(p))
        finally:
            conn.close()
        return RedirectResponse("/", status_code=303)

    @router.post("/pick-file")
    def pick_file() -> Response:
        """OS のファイル選択ダイアログを開き、選ばれた絶対パスを返す（ローカル実行前提）。"""
        return JSONResponse({"path": _pick_file_dialog()})

    @router.post("/documents/{doc_id}/delete")
    def delete_document(doc_id: str) -> Response:
        conn = db.connect(config.db_path)
        try:
            store.delete_document(conn, doc_id)
        finally:
            conn.close()
        return RedirectResponse("/", status_code=303)

    @router.get("/documents/{doc_id}")
    def view_document(request: Request, doc_id: str) -> Response:
        doc = _get_doc(doc_id)
        if doc is None:
            # 元ファイルの不在ではなく「その文書レジストリが無い」= 古いリンク等。
            return RedirectResponse("/?err=docgone", status_code=303)
        exists = Path(doc.path).is_file()
        if doc.doc_type == DOC_PDF:
            return templates.TemplateResponse(
                request, "viewer_pdf.html", {"doc": doc, "missing": not exists}
            )
        if doc.doc_type == DOC_HTML:
            return templates.TemplateResponse(
                request,
                "viewer_html.html",
                {"doc": doc, "missing": not exists, "src_name": Path(doc.path).name},
            )
        # Markdown
        text = _read_text(doc.path)
        if text is None:
            return templates.TemplateResponse(
                request, "viewer_md.html", {"doc": doc, "missing": True, "body": "", "clozes": []}
            )
        return templates.TemplateResponse(
            request,
            "viewer_md.html",
            {
                "doc": doc,
                "missing": False,
                "body": mdcloze.render_html(text),
                "clozes": mdcloze.list_clozes(text),
            },
        )

    # ---- Markdown: クローズ（元ファイルの記法が正本） ----
    @router.post("/documents/{doc_id}/cloze")
    def add_cloze(
        doc_id: str,
        line_start: int = Form(...),
        line_end: int = Form(...),
        selected: str = Form(...),
        occurrence: int = Form(0),
    ) -> Response:
        doc = _get_doc(doc_id)
        if doc is None:
            return JSONResponse({"ok": False, "error": "文書が見つかりません。"}, status_code=404)
        text = _read_text(doc.path)
        if text is None:
            return JSONResponse(
                {"ok": False, "error": "元ファイルが見つかりません。"}, status_code=404
            )
        new_text, error = mdcloze.insert_cloze(text, line_start, line_end, selected, occurrence)
        if error:
            return JSONResponse({"ok": False, "error": error})
        _write_text(doc.path, new_text)
        return JSONResponse({"ok": True, "error": ""})

    @router.post("/documents/{doc_id}/cloze/delete")
    def delete_cloze(doc_id: str, number: int = Form(...)) -> Response:
        doc = _get_doc(doc_id)
        if doc is None:
            return JSONResponse({"ok": False, "error": "文書が見つかりません。"}, status_code=404)
        text = _read_text(doc.path)
        if text is None:
            return JSONResponse(
                {"ok": False, "error": "元ファイルが見つかりません。"}, status_code=404
            )
        _write_text(doc.path, mdcloze.remove_cloze(text, number))
        return JSONResponse({"ok": True, "error": ""})

    # ---- PDF: 元ファイル配信と穴（DB 管理） ----
    @router.get("/documents/{doc_id}/raw")
    def raw_document(doc_id: str) -> Response:
        doc = _get_doc(doc_id)
        if doc is None or doc.doc_type != DOC_PDF:
            return JSONResponse({"error": "not found"}, status_code=404)
        p = Path(doc.path)
        if not p.is_file():
            return JSONResponse({"error": "missing"}, status_code=404)
        return FileResponse(p, media_type="application/pdf", filename=p.name)

    @router.get("/documents/{doc_id}/blanks")
    def list_blanks(doc_id: str) -> Response:
        conn = db.connect(config.db_path)
        try:
            blanks = pdfblanks.list_blanks(conn, doc_id)
            counts = attempts.counts_for_doc(conn, doc_id)
        finally:
            conn.close()
        return JSONResponse(
            {
                "blanks": [
                    {
                        "id": b.id,
                        "page": b.page,
                        "kind": b.kind,
                        "rects": b.rects,
                        "note": b.note,
                        "counts": counts.get(b.id, {"correct": 0, "incorrect": 0}),
                    }
                    for b in blanks
                ]
            }
        )

    @router.post("/documents/{doc_id}/blanks")
    def add_blank(
        doc_id: str,
        page: int = Form(...),
        kind: str = Form(...),
        rects: str = Form(...),
    ) -> Response:
        doc = _get_doc(doc_id)
        if doc is None:
            return JSONResponse({"ok": False, "error": "文書が見つかりません。"}, status_code=404)
        try:
            parsed = json.loads(rects)
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "error": "矩形データが不正です。"})
        conn = db.connect(config.db_path)
        try:
            blank, error = pdfblanks.add_blank(conn, doc_id, page, kind, parsed)
        finally:
            conn.close()
        if error or blank is None:
            return JSONResponse({"ok": False, "error": error})
        return JSONResponse(
            {
                "ok": True,
                "error": "",
                "blank": {
                    "id": blank.id,
                    "page": blank.page,
                    "kind": blank.kind,
                    "rects": blank.rects,
                },
            }
        )

    @router.post("/documents/{doc_id}/blanks/{blank_id}/delete")
    def delete_blank(doc_id: str, blank_id: str) -> Response:
        conn = db.connect(config.db_path)
        try:
            pdfblanks.delete_blank(conn, doc_id, blank_id)
            attempts.delete_for_blank(conn, doc_id, blank_id)
        finally:
            conn.close()
        return JSONResponse({"ok": True, "error": ""})

    @router.post("/documents/{doc_id}/blanks/{blank_id}/note")
    def set_blank_note(doc_id: str, blank_id: str, note: str = Form("")) -> Response:
        conn = db.connect(config.db_path)
        try:
            pdfblanks.set_note(conn, doc_id, blank_id, note)
        finally:
            conn.close()
        return JSONResponse({"ok": True, "error": "", "note": note})

    # ---- HTML: 同一オリジン配信（資材）と穴（DB 管理） ----
    @router.get("/documents/{doc_id}/asset/{rel:path}")
    def html_asset(doc_id: str, rel: str) -> Response:
        doc = _get_doc(doc_id)
        if doc is None or doc.doc_type != DOC_HTML:
            return JSONResponse({"error": "not found"}, status_code=404)
        target = _resolve_asset(doc.path, rel)
        if target is None:
            return JSONResponse({"error": "missing"}, status_code=404)
        # 外部資材の読み込みは許容する（別ページへの遷移の固定は htmlviewer.js が担う）。
        return FileResponse(target)

    @router.get("/documents/{doc_id}/html-blanks")
    def list_html_blanks(doc_id: str) -> Response:
        conn = db.connect(config.db_path)
        try:
            blanks = htmlblanks.list_blanks(conn, doc_id)
            counts = attempts.counts_for_doc(conn, doc_id)
        finally:
            conn.close()
        return JSONResponse(
            {
                "blanks": [
                    {
                        "id": b.id,
                        "kind": b.kind,
                        "payload": b.payload,
                        "note": b.note,
                        "counts": counts.get(b.id, {"correct": 0, "incorrect": 0}),
                    }
                    for b in blanks
                ]
            }
        )

    @router.post("/documents/{doc_id}/html-blanks")
    def add_html_blank(
        doc_id: str,
        kind: str = Form(...),
        payload: str = Form(...),
    ) -> Response:
        doc = _get_doc(doc_id)
        if doc is None:
            return JSONResponse({"ok": False, "error": "文書が見つかりません。"}, status_code=404)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "error": "アンカー情報が不正です。"})
        if not isinstance(parsed, dict):
            return JSONResponse({"ok": False, "error": "アンカー情報が不正です。"})
        conn = db.connect(config.db_path)
        try:
            blank, error = htmlblanks.add_blank(conn, doc_id, kind, parsed)
        finally:
            conn.close()
        if error or blank is None:
            return JSONResponse({"ok": False, "error": error})
        return JSONResponse(
            {
                "ok": True,
                "error": "",
                "blank": {"id": blank.id, "kind": blank.kind, "payload": blank.payload},
            }
        )

    @router.post("/documents/{doc_id}/html-blanks/{blank_id}/delete")
    def delete_html_blank(doc_id: str, blank_id: str) -> Response:
        conn = db.connect(config.db_path)
        try:
            htmlblanks.delete_blank(conn, doc_id, blank_id)
            attempts.delete_for_blank(conn, doc_id, blank_id)
        finally:
            conn.close()
        return JSONResponse({"ok": True, "error": ""})

    @router.post("/documents/{doc_id}/html-blanks/{blank_id}/note")
    def set_html_blank_note(doc_id: str, blank_id: str, note: str = Form("")) -> Response:
        conn = db.connect(config.db_path)
        try:
            htmlblanks.set_note(conn, doc_id, blank_id, note)
        finally:
            conn.close()
        return JSONResponse({"ok": True, "error": "", "note": note})

    # ---- 正誤記録（PDF/HTML 共通。blank_id をキーに履歴を残す） ----
    @router.post("/documents/{doc_id}/attempts")
    def add_attempt(
        doc_id: str,
        blank_id: str = Form(...),
        result: str = Form(...),
    ) -> Response:
        conn = db.connect(config.db_path)
        try:
            counts, error = attempts.record(conn, doc_id, blank_id, result)
        finally:
            conn.close()
        if error or counts is None:
            return JSONResponse({"ok": False, "error": error})
        return JSONResponse({"ok": True, "error": "", "counts": counts})

    return router
