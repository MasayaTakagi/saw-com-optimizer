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

## ディレクトリ

- `saw-com-optimizer/src/` — モデル、回路計算、最適化、レポート生成
- `saw-com-optimizer/configs/` — 探索条件とモデル設定
- `saw-com-optimizer/tests/` — 単体テスト・統合テスト
- `saw-com-optimizer/scripts/` — 探索ランチャーと解析スクリプト
- `saw-com-optimizer/docs/` — 設計・検証ドキュメント

`runs/` などの探索生成物はGit管理対象外です。
