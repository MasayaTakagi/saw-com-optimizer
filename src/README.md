# ソース構成

Pythonパッケージは `sawopt/`。責務は次のとおり。

- `sawopt/core/`: COM区間、素子モデル、回路合成、2ポート変換、特性評価
- `sawopt/problem/`: 設計空間、設計の canonical 化、物理評価、検証
- `sawopt/optimizers/`: SciPy-DE、L-SHADE、比較・ランキング、連続 polish
- `sawopt/optimization/`: accounting、予算、頻度調整、cache、収束証跡、履歴、population、runner、SAW固有の探索サービス
- `sawopt/studies/`: 現行のDMS topology screening、Hybrid、共通study helper、L-SHADE記録変換
- `sawopt/io/`: 設定解決、JSON serialization、run manifest/provenance
- `sawopt/runtime/`: BLAS thread 制御など実行環境の境界
- `sawopt/reporting/`: 保存済み結果からのHTML・CSV・図の生成
- `sawopt/__main__.py`: 基本 CLI と config-driven `run-study` の入口

`python -m sawopt run-study` はDMS topology screeningを実行する。50 Ω Hybridは
`python -m sawopt.studies.hybrid` から実行する。基本CLIとPowerShellランチャーも利用できる。
