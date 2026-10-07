# スクリプト構成

## 実行環境と成果物の保存先

正式環境はWSL2 Ubuntu + VS Code Remote WSL + Codex CLI + uvです。
新規worktreeでは `uv sync --locked --extra test` を実行してください。
詳細は [開発環境](../docs/guides/development_environment.md) を参照してください。

このディレクトリのPowerShellランチャーは旧Windows保存run向けの歴史的な
補助ツールです。正式なWSL入口ではなく、Windows専用 `.venv` が既にある
場合に限って利用します。新規Windows環境を作成する手順は提供しません。

レビュー用ZIPはプロジェクトroot直下の
`artifacts/review_bundles/` に固定し、`runs/` には保存しません。

- `common/`: すべてのPowerShellランチャーが共有する環境設定とPython起動処理
- `launchers/`: 解析・試行ごとの利用者向け起動ファイル
- `analysis/`: 保存結果の解析

旧Windows向けの入口は次の2つ。

- `launchers/base-study.ps1`: 基本COMシミュレーションとインピーダンススイープ
- `launchers/hybrid-50ohm.ps1`: 50 Ω固定のDMS＋ラダー探索

現在のDMS topology studyは `uv run --locked python -m sawopt run-study --config
configs/studies/dms_topology_screening.yaml --run runs/<name>` から実行します。
30分以上かかる本番runは `uv run --locked python -m sawopt.orchestration.cli launch` を使います。
