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
- `analysis/`: 保存結果の解析

通常利用する入口は次の3つ。

- `launchers/base-study.ps1`: 基本COMシミュレーションとインピーダンススイープ
- `launchers/hybrid-50ohm.ps1`: 50 Ω固定のDMS＋ラダー探索

現在のDMS topology studyは `python -m sawopt run-study --config
configs/studies/dms_topology_screening.yaml --run runs/<name>` から実行します。
30分以上かかる本番runは `python -m sawopt.orchestration.cli launch` を使います。
