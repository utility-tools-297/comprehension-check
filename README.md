# comprehension-check

ローカルに保存した文書（Markdown / PDF / HTML）を元レイアウトのまま閲覧しながら、任意の箇所を
穴埋め（クローズ）として隠し、理解度を確認するためのローカル Web アプリ。元文書をそのまま読み進め、
文脈の中で穴埋めを解けることを重視する（単語帳的な再構成はしない）。

使い方は SETUP.md、原点の構想は CONCEPT.md を参照。

## 現状（Markdown / PDF / HTML 対応）

- 対応形式は **Markdown・PDF・HTML**。
- 実践モード共通: 穴は既定で全て隠れ、クリックで表示/再度非表示。「全て表示」「全て隠す」あり。状態は保存しない。
- **Markdown**: 穴の正本は元ファイル内の記法 `{{cN::answer}}`（DB に持たない）。作成は外部エディタで直接記入／
  アプリ上で文章を選択して記法を元ファイルへ書き込む、の両方。
- **PDF**: 元ファイルは不変で、穴は DB 管理（ページ内の正規化矩形）。PDF.js で元レイアウトのまま表示。作成は
  「テキスト選択」と「矩形」（図・画像向け）の2方式。マスクをクリックで開閉、作成モードでは削除。
- **HTML**: 元ファイルは不変で、穴は DB 管理。元 HTML を同一オリジンで iframe 表示（レイアウト維持）。
  リフロー耐性のため穴はアンカーで保持（text＝前後文脈つきテキスト／rect＝対象要素内の正規化矩形）。

## フォルダ・ファイル構成

```
comprehension-check/
├── README.md                 # 本ファイル。概要＋構成
├── SETUP.md                  # 実行手順
├── CONCEPT.md                # 構想メモ
├── pyproject.toml / uv.lock  # パッケージ定義・依存ロック（uv 管理）
├── docs/design.md            # 設計・実装フェーズ・既知の制約
├── src/comprehension_check/  # 本体（FastAPI アプリ。入口 __main__.py）
│   ├── config.py             #   設定（データ保存先・ホスト/ポート）
│   ├── web.py                #   アプリ組み立て（静的・テンプレート・ルータ）
│   ├── routes.py             #   HTTP ルート（一覧・登録・ビューア・穴操作）
│   ├── db.py / store.py      #   SQLite 接続と文書レジストリ CRUD
│   ├── ids.py                #   ID・時刻文字列の生成（共通）
│   ├── models.py             #   Document / Cloze / Blank
│   ├── mdcloze.py            #   Markdown 描画・記法の挿入/削除
│   ├── pdfblanks.py          #   PDF の穴 CRUD・重なり判定
│   ├── htmlblanks.py         #   HTML の穴 CRUD（テキストアンカー / 要素基準の矩形）
│   ├── templates/            #   Jinja2（base / index / viewer_md / viewer_pdf / viewer_html）
│   └── static/               #   style.css / app.js / pdfviewer.js / htmlviewer.js / vendor/pdfjs（同梱）
├── data/                     # SQLite(app.db) 置き場（README のみ git 管理）
├── run/run_app.bat           # 起動バッチ（Windows）
└── tests/                    # pytest（mdcloze / pdfblanks / HTTP スモーク）
```

## 起動

```
uv sync
uv run python -m comprehension_check
```

既定で `http://localhost:8020`。**このPCからのみ**アクセス可（ループバック 127.0.0.1 で待受。
同一 LAN や Tailscale 等の他端末からは接続できない）。

## セキュリティと免責

- 本ツールは、登録した HTML 文書を iframe で**同一オリジン表示**し、元レイアウト再現のため
  その文書自身の JavaScript を実行する。したがって **信頼できる自分の文書だけを登録する**ことを
  前提とする。素性の分からない HTML は登録しないこと。
- ループバック（127.0.0.1）でのみ待受し、文書内容を外部へ送信する機能は持たない。
- 本ソフトウェアは「現状のまま（AS IS）」提供され、**無保証・自己責任**で利用するもの。
  利用により生じたいかなる損害についても作者は責任を負わない（詳細はルートの `LICENSE`）。

## ライセンス

- 本体: MIT License（ルートの `LICENSE`）。
- 同梱の PDF.js は Apache License 2.0（`src/comprehension_check/static/vendor/pdfjs/README.md` を参照）。
