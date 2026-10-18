"""アプリ設定（データ保存先・待ち受けホスト/ポート）。

個人利用のローカルサーバ。設定値は少数なので dataclass の既定値で持ち、
必要になった時点で config ファイル読み込みを足す方針。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# src/comprehension_check/
PACKAGE_DIR = Path(__file__).resolve().parent
# プロジェクトルート（src/ の2つ上）
PROJECT_ROOT = PACKAGE_DIR.parents[1]


@dataclass
class Config:
    """アプリ全体の設定。"""

    data_dir: Path
    # ループバックのみ待ち受け＝このPCからのみアクセス可（LAN/Tailscale等の他端末からは到達不能）。
    host: str = "127.0.0.1"
    port: int = 8020

    @property
    def db_path(self) -> Path:
        """文書レジストリ等を収める SQLite ファイルのパス。"""
        return self.data_dir / "app.db"

    @classmethod
    def default(cls) -> Config:
        """既定設定（データはプロジェクト直下 data/ に置く）。"""
        return cls(data_dir=PROJECT_ROOT / "data")
