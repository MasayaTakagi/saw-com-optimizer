# テスト構成

- `unit/core/`: COM、ネットワーク、ラダー回路、数値回帰
- `unit/optimization/`: 探索ポリシー、適応周波数、キャッシュ、目的関数
- `integration/`: run再開、試行オーケストレーション、レポート連携

正式環境はWSL2 Ubuntu 24.04上のUbuntu system Python 3.12＋uvです。
新しいworktreeのルートで依存関係を同期し、プロジェクトのテストを実行します。

```bash
uv sync --locked --extra test
uv run --locked pytest
```

各worktree直下の`.venv`はuvが自動生成・管理します。手動での仮想環境作成や
activateは不要です。WindowsネイティブPowerShellは正式なテスト実行手順ではありません。
新規本番のレビュー証拠は
`reports/experiment_reviews/<stage>/<run_id>/`に保存します。歴史的・アドホックな
保存済みrunのreview bundleは`artifacts/review_bundles/`に置けますが、
新規本番レビューの正規経路ではありません。
環境と証拠保存の詳細は、[開発環境ガイド](../docs/guides/development_environment.md)、
[レビュー方針](../docs/guides/data_storage_logging_review_policy.md)、
[review bundleガイド](../docs/guides/review_bundles.md)を参照してください。
