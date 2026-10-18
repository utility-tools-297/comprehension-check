"""実行入口: `uv run python -m comprehension_check` でローカルサーバを起動する。"""

import uvicorn

from comprehension_check.config import Config
from comprehension_check.web import create_app


def main() -> None:
    """既定設定でアプリを起動する。"""
    config = Config.default()
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
