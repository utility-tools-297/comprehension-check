"""ID と時刻文字列の生成（レコード共通）。"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime


def now_string() -> str:
    """ローカル時刻の 'YYYY-MM-DD HH:MM:SS' 文字列（tz 対応で取得）。"""
    return datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def gen_id() -> str:
    """時刻＋乱数で衝突しにくい ID を作る。"""
    stamp = datetime.now(tz=UTC).astimezone().strftime("%Y%m%d%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"
