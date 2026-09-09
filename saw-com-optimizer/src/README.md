# ソース構成

Pythonパッケージは `sawopt/`。役割は次のとおり。

- `sawopt/core/`: COM区間、素子モデル、回路合成、2ポート変換、特性評価
- `sawopt/optimization/`: 基本探索、ハイブリッド探索、Stage 2共同探索、探索補助
- `sawopt/reporting/`: 保存済み結果からのHTML・CSV・図の生成
- `sawopt/__main__.py`: 基本CLIの入口

通常はモジュールを直接実行せず、`scripts/launchers/` のPowerShellファイルを使用する。
