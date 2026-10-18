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
