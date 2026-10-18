# repos_external

ハーネスとして、別の git リポジトリをローカル配置し subprocess で実行するための置き場。

- **clone した各リポジトリの中身は git 管理しない**（この README のみ管理）。
- どのリポジトリをどこから clone するか、実行方法（`git checkout <ref>` での版切替、PYTHONPATH や
  `uv run --project <repo>` での実行）は SETUP.md に記載する。
- import せず subprocess で丸ごと実行するため、相手のパッケージ化・install は不要。
