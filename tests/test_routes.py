"""HTTP ルートのスモークテスト（登録→閲覧→穴追加→削除）。"""

from pathlib import Path

from fastapi.testclient import TestClient

from comprehension_check.config import Config
from comprehension_check.web import create_app


def _client(tmp_path: Path) -> TestClient:
    """一時データディレクトリでアプリを立てる。"""
    app = create_app(Config(data_dir=tmp_path / "data"))
    return TestClient(app)


def _make_md(tmp_path: Path, text: str) -> Path:
    """テスト用の Markdown ファイルを作る。"""
    p = tmp_path / "note.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_register_view_and_cloze_roundtrip(tmp_path: Path) -> None:
    """登録→閲覧→穴の追加/削除が元ファイルへ反映される。"""
    md = _make_md(tmp_path, "日本の首都は東京都である。")
    client = _client(tmp_path)

    # 登録
    res = client.post(
        "/documents", data={"path": str(md), "title": "テスト"}, follow_redirects=False
    )
    assert res.status_code == 303

    # 一覧に出る
    res = client.get("/")
    assert "テスト" in res.text

    # 文書IDを取得
    app_config = Config(data_dir=tmp_path / "data")
    from comprehension_check import db, store

    conn = db.connect(app_config.db_path)
    docs = store.list_documents(conn)
    conn.close()
    assert len(docs) == 1
    doc_id = docs[0].id

    # 閲覧でマスク対象が無い状態
    res = client.get(f"/documents/{doc_id}")
    assert "東京都" in res.text

    # 穴を追加 → 元ファイルに記法が書かれる
    res = client.post(
        f"/documents/{doc_id}/cloze",
        data={"line_start": 0, "line_end": 1, "selected": "東京都", "occurrence": 0},
    )
    assert res.json()["ok"] is True
    assert md.read_text(encoding="utf-8") == "日本の首都は{{c1::東京都}}である。"

    # 閲覧で span 化される
    res = client.get(f"/documents/{doc_id}")
    assert 'data-cloze="1"' in res.text

    # 穴を削除 → 記法が外れる
    res = client.post(f"/documents/{doc_id}/cloze/delete", data={"number": 1})
    assert res.json()["ok"] is True
    assert md.read_text(encoding="utf-8") == "日本の首都は東京都である。"


def test_register_rejects_non_supported(tmp_path: Path) -> None:
    """対応外の拡張子は登録できない。"""
    other = tmp_path / "note.txt"
    other.write_text("x", encoding="utf-8")
    client = _client(tmp_path)
    res = client.post("/documents", data={"path": str(other)}, follow_redirects=False)
    assert res.status_code == 303
    assert "err=type" in res.headers["location"]


def _only_doc_id(tmp_path: Path) -> str:
    """DB に1件だけ登録されている文書の ID を返す。"""
    from comprehension_check import db, store

    conn = db.connect(Config(data_dir=tmp_path / "data").db_path)
    docs = store.list_documents(conn)
    conn.close()
    assert len(docs) == 1
    return docs[0].id


def test_pdf_register_view_raw_and_blanks(tmp_path: Path) -> None:
    """PDF の登録→ビューア表示→raw 配信→穴の追加/重なり拒否/削除。"""
    pdf = tmp_path / "textbook.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% dummy content for route test\n")
    client = _client(tmp_path)

    res = client.post("/documents", data={"path": str(pdf)}, follow_redirects=False)
    assert res.status_code == 303
    doc_id = _only_doc_id(tmp_path)

    # ビューアは PDF 用テンプレート
    res = client.get(f"/documents/{doc_id}")
    assert "pdfviewer.js" in res.text
    assert 'class="pdf-doc' in res.text

    # raw 配信
    res = client.get(f"/documents/{doc_id}/raw")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"

    # 穴の追加
    import json

    rects = json.dumps([{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05}])
    res = client.post(
        f"/documents/{doc_id}/blanks", data={"page": 1, "kind": "text", "rects": rects}
    )
    assert res.json()["ok"] is True

    # 一覧に出る
    res = client.get(f"/documents/{doc_id}/blanks")
    blanks = res.json()["blanks"]
    assert len(blanks) == 1
    blank_id = blanks[0]["id"]

    # 重なる穴は拒否
    overlap = json.dumps([{"x": 0.15, "y": 0.1, "w": 0.2, "h": 0.05}])
    res = client.post(
        f"/documents/{doc_id}/blanks", data={"page": 1, "kind": "rect", "rects": overlap}
    )
    assert res.json()["ok"] is False

    # 削除
    res = client.post(f"/documents/{doc_id}/blanks/{blank_id}/delete")
    assert res.json()["ok"] is True
    assert client.get(f"/documents/{doc_id}/blanks").json()["blanks"] == []


def test_html_register_view_asset_and_blanks(tmp_path: Path) -> None:
    """HTML の登録→ビューア表示→資材配信→穴の追加/重複拒否/削除。"""
    html = tmp_path / "page.html"
    html.write_text(
        "<!doctype html><html><body><p>価格は需要と供給で決まる。</p>"
        '<img src="fig.png" alt="図"></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "fig.png").write_bytes(b"\x89PNG\r\n\x1a\n dummy")
    client = _client(tmp_path)

    res = client.post("/documents", data={"path": str(html)}, follow_redirects=False)
    assert res.status_code == 303
    doc_id = _only_doc_id(tmp_path)

    # ビューアは HTML 用テンプレート（iframe + htmlviewer.js）
    res = client.get(f"/documents/{doc_id}")
    assert "htmlviewer.js" in res.text
    assert "html-frame" in res.text
    # 回帰防止: src はマークアップ出力（JS 代入だと sandbox フレームで描画されない個体がある）、
    # かつ allow-scripts 必須（無いと親の DOM 変更で描画が破棄され空白化する）。
    assert f"/documents/{doc_id}/asset/page.html" in res.text
    assert "allow-scripts" in res.text

    # 資材配信: HTML 本体と同階層の画像
    res = client.get(f"/documents/{doc_id}/asset/page.html")
    assert res.status_code == 200
    assert "需要と供給" in res.text
    res = client.get(f"/documents/{doc_id}/asset/fig.png")
    assert res.status_code == 200

    # 親フォルダへの遡上は拒否
    res = client.get(f"/documents/{doc_id}/asset/../secret.txt")
    assert res.status_code in (404, 400)

    # 穴（テキストアンカー）の追加
    import json

    payload = json.dumps({"exact": "需要と供給", "prefix": "価格は", "suffix": "で決まる"})
    res = client.post(f"/documents/{doc_id}/html-blanks", data={"kind": "text", "payload": payload})
    assert res.json()["ok"] is True

    res = client.get(f"/documents/{doc_id}/html-blanks")
    blanks = res.json()["blanks"]
    assert len(blanks) == 1
    blank_id = blanks[0]["id"]

    # 同一アンカーの重複は拒否
    res = client.post(f"/documents/{doc_id}/html-blanks", data={"kind": "text", "payload": payload})
    assert res.json()["ok"] is False

    # 削除
    res = client.post(f"/documents/{doc_id}/html-blanks/{blank_id}/delete")
    assert res.json()["ok"] is True
    assert client.get(f"/documents/{doc_id}/html-blanks").json()["blanks"] == []


def test_attempts_record_counts_and_cascade(tmp_path: Path) -> None:
    """穴に正誤を記録→一覧の counts に反映→穴削除で履歴も消える。"""
    import json

    pdf = tmp_path / "textbook.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    client = _client(tmp_path)
    client.post("/documents", data={"path": str(pdf)}, follow_redirects=False)
    doc_id = _only_doc_id(tmp_path)

    rects = json.dumps([{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05}])
    res = client.post(
        f"/documents/{doc_id}/blanks", data={"page": 1, "kind": "rect", "rects": rects}
    )
    blank_id = res.json()["blank"]["id"]

    # 初期は 0。
    blanks = client.get(f"/documents/{doc_id}/blanks").json()["blanks"]
    assert blanks[0]["counts"] == {"correct": 0, "incorrect": 0}

    # 記録して集計が返り、一覧にも反映される。
    res = client.post(
        f"/documents/{doc_id}/attempts", data={"blank_id": blank_id, "result": "correct"}
    )
    assert res.json()["ok"] is True
    assert res.json()["counts"] == {"correct": 1, "incorrect": 0}
    client.post(f"/documents/{doc_id}/attempts", data={"blank_id": blank_id, "result": "incorrect"})
    blanks = client.get(f"/documents/{doc_id}/blanks").json()["blanks"]
    assert blanks[0]["counts"] == {"correct": 1, "incorrect": 1}

    # 不正な結果種別は拒否。
    res = client.post(f"/documents/{doc_id}/attempts", data={"blank_id": blank_id, "result": "x"})
    assert res.json()["ok"] is False

    # 穴を消すと履歴も消える（再登録して記録 0 を確認）。
    client.post(f"/documents/{doc_id}/blanks/{blank_id}/delete")
    res = client.post(
        f"/documents/{doc_id}/blanks", data={"page": 1, "kind": "rect", "rects": rects}
    )
    new_id = res.json()["blank"]["id"]
    blanks = client.get(f"/documents/{doc_id}/blanks").json()["blanks"]
    assert blanks[0]["id"] == new_id
    assert blanks[0]["counts"] == {"correct": 0, "incorrect": 0}


def test_pdf_blank_note_roundtrip(tmp_path: Path) -> None:
    """PDF の穴にメモを保存でき、一覧の note に反映される。"""
    import json

    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    client = _client(tmp_path)
    client.post("/documents", data={"path": str(pdf)}, follow_redirects=False)
    doc_id = _only_doc_id(tmp_path)
    rects = json.dumps([{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05}])
    res = client.post(
        f"/documents/{doc_id}/blanks", data={"page": 1, "kind": "rect", "rects": rects}
    )
    blank_id = res.json()["blank"]["id"]

    assert client.get(f"/documents/{doc_id}/blanks").json()["blanks"][0]["note"] == ""
    res = client.post(f"/documents/{doc_id}/blanks/{blank_id}/note", data={"note": "覚える"})
    assert res.json()["ok"] is True
    assert client.get(f"/documents/{doc_id}/blanks").json()["blanks"][0]["note"] == "覚える"


def test_html_blank_note_roundtrip(tmp_path: Path) -> None:
    """HTML の穴にメモを保存でき、一覧の note に反映される。"""
    import json

    html = tmp_path / "page.html"
    html.write_text(
        "<!doctype html><html><body><p>需要と供給で決まる。</p></body></html>", encoding="utf-8"
    )
    client = _client(tmp_path)
    client.post("/documents", data={"path": str(html)}, follow_redirects=False)
    doc_id = _only_doc_id(tmp_path)
    payload = json.dumps({"exact": "需要と供給", "prefix": "", "suffix": "で決まる"})
    res = client.post(f"/documents/{doc_id}/html-blanks", data={"kind": "text", "payload": payload})
    blank_id = res.json()["blank"]["id"]

    assert client.get(f"/documents/{doc_id}/html-blanks").json()["blanks"][0]["note"] == ""
    res = client.post(f"/documents/{doc_id}/html-blanks/{blank_id}/note", data={"note": "重要"})
    assert res.json()["ok"] is True
    assert client.get(f"/documents/{doc_id}/html-blanks").json()["blanks"][0]["note"] == "重要"


def test_add_document_strips_quotes_and_reports_tried_path(tmp_path: Path) -> None:
    """引用符付きパスでも登録でき、失敗時は試したパスを表示する。"""
    md = tmp_path / "note.md"
    md.write_text("本文", encoding="utf-8")
    client = _client(tmp_path)

    # ダブルクォートで囲まれていても登録成功。
    res = client.post("/documents", data={"path": f'"{md}"'}, follow_redirects=False)
    assert res.status_code == 303

    # 存在しないパスは、試したパスを添えて知らせる（200 で一覧を再表示）。
    bad = str(tmp_path / "missing.md")
    res = client.post("/documents", data={"path": bad}, follow_redirects=False)
    assert res.status_code == 200
    assert "見つかりません" in res.text
    assert "missing.md" in res.text


def test_add_document_diagnosis_lists_folder_files(tmp_path: Path) -> None:
    """見つからない時、同じフォルダ内の実ファイル名を候補として表示する。"""
    real = tmp_path / "実在ファイル.html"
    real.write_text("<html><body>x</body></html>", encoding="utf-8")
    client = _client(tmp_path)

    # 同じフォルダの別名（存在しない）を指定 → フォルダ内の実ファイル名が出る。
    wrong = str(tmp_path / "typo.html")
    res = client.post("/documents", data={"path": wrong}, follow_redirects=False)
    assert res.status_code == 200
    assert "実在ファイル.html" in res.text  # 実ファイル名が候補として提示される

    # 存在しないフォルダは、その旨を知らせる。
    res = client.post("/documents", data={"path": r"Z:\no\such\dir\x.html"}, follow_redirects=False)
    assert res.status_code == 200
    assert "フォルダ" in res.text


def test_qa_create_generates_md_and_registers(tmp_path: Path) -> None:
    """作問ツール：Q&A→答えを穴にした .md を生成・登録し、ビューアで問題が見え答えが穴になる。"""
    import json

    client = _client(tmp_path)
    items = json.dumps([{"question": "日本の首都は？", "answer": "東京"}])
    res = client.post("/qa", data={"title": "地理", "items": items}, follow_redirects=False)
    assert res.status_code == 303
    loc = res.headers["location"]
    assert loc.startswith("/documents/")

    view = client.get(loc)
    assert "日本の首都は？" in view.text  # 問題は見える
    assert 'data-cloze="1"' in view.text  # 答えは穴
    assert "cc:qa" not in view.text  # マーカーは画面に出ない

    files = list((tmp_path / "data" / "generated").glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert text.startswith("<!-- cc:qa -->")
    assert "{{c1::東京}}" in text


def test_md_attempt_note_and_blanks_roundtrip(tmp_path: Path) -> None:
    """Markdown の穴に正誤を記録し、メモを保存でき、md-blanks に反映される。"""
    md = _make_md(tmp_path, "首都は{{c1::東京}}。")
    client = _client(tmp_path)
    client.post("/documents", data={"path": str(md)}, follow_redirects=False)
    doc_id = _only_doc_id(tmp_path)

    blanks = client.get(f"/documents/{doc_id}/md-blanks").json()["clozes"]
    assert blanks == [{"number": 1, "counts": {"correct": 0, "incorrect": 0}, "note": ""}]

    res = client.post(f"/documents/{doc_id}/md-attempts", data={"number": 1, "result": "correct"})
    assert res.json()["ok"] is True
    assert res.json()["counts"] == {"correct": 1, "incorrect": 0}

    # 存在しない穴番号は拒否。
    res = client.post(f"/documents/{doc_id}/md-attempts", data={"number": 9, "result": "correct"})
    assert res.json()["ok"] is False

    client.post(f"/documents/{doc_id}/md-note", data={"number": 1, "note": "重要"})
    blanks = client.get(f"/documents/{doc_id}/md-blanks").json()["clozes"]
    assert blanks[0]["counts"] == {"correct": 1, "incorrect": 0}
    assert blanks[0]["note"] == "重要"


def test_qa_edit_reorder_preserves_meta_and_delete_removes_it(tmp_path: Path) -> None:
    """Q&A編集：並べ替えでも回数・メモが穴に追従し、削除した問のメタは消える。"""
    import json

    client = _client(tmp_path)
    items = json.dumps([{"question": "Q1", "answer": "A1"}, {"question": "Q2", "answer": "A2"}])
    loc = client.post("/qa", data={"title": "t", "items": items}, follow_redirects=False).headers[
        "location"
    ]
    doc_id = loc.rsplit("/", 1)[1]

    client.post(f"/documents/{doc_id}/md-attempts", data={"number": 2, "result": "correct"})
    client.post(f"/documents/{doc_id}/md-note", data={"number": 1, "note": "m1"})

    # 並べ替え（2を先頭へ）。番号は維持される。
    reordered = json.dumps(
        [
            {"number": 2, "question": "Q2", "answer": "A2"},
            {"number": 1, "question": "Q1", "answer": "A1"},
        ]
    )
    assert client.post(f"/documents/{doc_id}/qa", data={"items": reordered}).json()["ok"] is True
    blanks = {b["number"]: b for b in client.get(f"/documents/{doc_id}/md-blanks").json()["clozes"]}
    assert blanks[2]["counts"] == {"correct": 1, "incorrect": 0}  # 並べ替えても追従
    assert blanks[1]["note"] == "m1"

    # 問(number=1)を削除 → そのメタが消え、number=2 は残る。
    only2 = json.dumps([{"number": 2, "question": "Q2", "answer": "A2"}])
    client.post(f"/documents/{doc_id}/qa", data={"items": only2})
    clozes = client.get(f"/documents/{doc_id}/md-blanks").json()["clozes"]
    assert {c["number"] for c in clozes} == {2}
    assert clozes[0]["counts"] == {"correct": 1, "incorrect": 0}


def test_cloze_delete_removes_md_meta(tmp_path: Path) -> None:
    """手書き Markdown でも、穴の削除で正誤回数・メモが消える。"""
    md = _make_md(tmp_path, "首都は{{c1::東京}}。")
    client = _client(tmp_path)
    client.post("/documents", data={"path": str(md)}, follow_redirects=False)
    doc_id = _only_doc_id(tmp_path)

    client.post(f"/documents/{doc_id}/md-attempts", data={"number": 1, "result": "correct"})
    client.post(f"/documents/{doc_id}/md-note", data={"number": 1, "note": "x"})

    assert client.post(f"/documents/{doc_id}/cloze/delete", data={"number": 1}).json()["ok"] is True
    assert client.get(f"/documents/{doc_id}/md-blanks").json()["clozes"] == []


def test_qa_editor_pages_render(tmp_path: Path) -> None:
    """作問フォーム（新規）と編集エディタ（既存Q&A）が描画できる。"""
    import json

    client = _client(tmp_path)
    new_page = client.get("/qa/new")
    assert new_page.status_code == 200
    assert "qaeditor.js" in new_page.text

    items = json.dumps([{"question": "Q1", "answer": "A1"}])
    loc = client.post("/qa", data={"title": "t", "items": items}, follow_redirects=False).headers[
        "location"
    ]
    doc_id = loc.rsplit("/", 1)[1]

    editor = client.get(f"/documents/{doc_id}/qa")
    assert editor.status_code == 200
    assert "qaeditor.js" in editor.text
    assert "A1" in editor.text  # 既存の答えが初期値として埋め込まれる

    # ビューアには「Q&A編集」導線があり、手書きMDには出ない。
    assert f"/documents/{doc_id}/qa" in client.get(f"/documents/{doc_id}").text
    md = _make_md(tmp_path, "本文{{c1::語}}")
    client.post("/documents", data={"path": str(md)}, follow_redirects=False)
    from comprehension_check import db, store

    conn = db.connect(Config(data_dir=tmp_path / "data").db_path)
    plain = next(d.id for d in store.list_documents(conn) if d.id != doc_id)
    conn.close()
    assert "Q&A編集" not in client.get(f"/documents/{plain}").text
