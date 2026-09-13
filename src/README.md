# ソース構成

Pythonパッケージは `sawopt/`。責務は次のとおり。

- `sawopt/core/`: COM区間、素子モデル、回路合成、2ポート変換、特性評価
- `sawopt/problem/`: 設計空間、設計の canonical 化、物理評価、検証
- `sawopt/optimizers/`: SciPy-DE、L-SHADE、比較・ランキング、連続 polish
- `sawopt/optimization/`: 予算、履歴、頻度交換、cache、runner などの再利用サービス
- `sawopt/studies/`: topology screening、convergence、continuation、optimizer A/B、pre-production の protocol
- `sawopt/io/`: 設定解決、JSON serialization、run manifest/provenance
- `sawopt/runtime/`: BLAS thread 制御など実行環境の境界
- `sawopt/reporting/`: 保存済み結果からのHTML・CSV・図の生成
- `sawopt/__main__.py`: 基本 CLI と config-driven `run-study` の入口

通常は `experiments/*/experiment.yaml` を `python -m sawopt run-study` に渡すか、
`scripts/launchers/` の PowerShell ランチャーを使用する。旧 Stage module path は
移行期間の互換 shim として残している。
