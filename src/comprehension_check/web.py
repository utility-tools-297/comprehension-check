"""FastAPI アプリの組み立て。

設定を受け取り、静的ファイル・テンプレート・ルータを載せたアプリを返す。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import Response

from comprehension_check import routes
from comprehension_check.config import Config

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def create_app(config: Config) -> FastAPI:
    """設定からアプリを構築して返す。"""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="comprehension-check")

    # ローカル専用ツール。ブラウザに一切キャッシュさせず、常に最新の
    # ページ・JS/CSS を配信する（古い静的ファイルを掴んで不整合になるのを防ぐ）。
    @app.middleware("http")
    async def _no_cache(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.include_router(routes.build_router(config, templates))
    return app
