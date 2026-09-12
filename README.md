# SAW COM インピーダンス探索プロジェクト

SAW COMモデルのインピーダンス探索プロトタイプです。実装・設定・検証コードは [`saw-com-optimizer/`](saw-com-optimizer/) にあります。

## クイックスタート

必要なPythonバージョンは3.11以上です。

```powershell
cd saw-com-optimizer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pytest
```

詳しい使い方は [プロジェクトREADME](saw-com-optimizer/README.md) と [docs/](saw-com-optimizer/docs/) を参照してください。

外部AIレビュー用の資料は `handoff/` に、生成したレビューZIPはこのルート直下の
`review_bundles/` に保存します。レビューZIPは生成物のためGit管理対象外です。

## ディレクトリ

- `saw-com-optimizer/src/` — モデル、回路計算、最適化、レポート生成
- `saw-com-optimizer/configs/` — 探索条件とモデル設定
- `saw-com-optimizer/tests/` — 単体テスト・統合テスト
- `saw-com-optimizer/scripts/` — 探索ランチャーと解析スクリプト
- `saw-com-optimizer/docs/` — 設計・検証ドキュメント
- `handoff/` — 外部AIレビューに渡す計画書・前提資料
- `review_bundles/` — 外部レビュー用に生成したZIP（Git管理対象外）

`runs/` や `review_bundles/` などの生成物はGit管理対象外です。

## 実行環境とレビューZIPの保存先

通常の実行には、`saw-com-optimizer/.venv/` を使用します。PowerShellでは
プロジェクトの仮想環境を有効化してから、`python` を実行してください。
ランチャーもこの仮想環境を既定で使用し、システムPythonや同梱ランタイムへ
自動フォールバックしません。

```powershell
Set-Location .\saw-com-optimizer
if (-not (Test-Path .\.venv\Scripts\python.exe)) { py -3 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

外部AIレビュー用ZIPの生成先は、常にこのREADMEのあるルート直下の
`review_bundles/` です。`saw-com-optimizer/runs/` やプロジェクト配下に
保存しないでください。
