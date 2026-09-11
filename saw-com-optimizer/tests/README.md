# テスト構成

- `unit/core/`: COM、ネットワーク、ラダー回路、数値回帰
- `unit/optimization/`: 探索ポリシー、適応周波数、キャッシュ、目的関数
- `integration/`: run再開、試行オーケストレーション、レポート連携

プロジェクトルートから次を実行する。

```powershell
python -m pytest -q
```
