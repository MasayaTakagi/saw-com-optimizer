# スクリプト構成

## 実行環境と成果物の保存先

PowerShellランチャーは、プロジェクト直下の `.venv\Scripts\python.exe` を
既定のPythonとして使用します。未作成の場合は、プロジェクトディレクトリで
次を一度実行してください。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

レビュー用ZIPはプロジェクトroot直下の
`artifacts/review_bundles/` に固定し、`runs/` には保存しません。

- `common/`: すべてのPowerShellランチャーが共有する環境設定とPython起動処理
- `launchers/`: 解析・試行ごとの利用者向け起動ファイル
- `analysis/`: 保存結果の解析と探索品質ベンチマーク
- `maintenance/`: 過去runの監査メタデータを更新する一度限りの保守処理

通常利用する入口は次の3つ。

- `launchers/base-study.ps1`: 基本COMシミュレーションとインピーダンススイープ
- `launchers/hybrid-50ohm.ps1`: 50 Ω固定のDMS＋ラダー探索
- `launchers/stage2-study.ps1`: 構成・結線・インピーダンスの共同探索

新しい実験は仮想環境を有効にした上で、`PYTHONPATH=src python -m sawopt
run-study --config experiments/<name>/experiment.yaml --run runs/<name>` を使う。上記 launcher と
旧 Stage module invocation は既存 workflow の互換入口である。

`maintenance/` のスクリプトは通常の試行には使用しない。
