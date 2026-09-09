# スクリプト構成

- `common/`: すべてのPowerShellランチャーが共有する環境設定とPython起動処理
- `launchers/`: 解析・試行ごとの利用者向け起動ファイル
- `analysis/`: 保存結果の解析と探索品質ベンチマーク
- `maintenance/`: 過去runの監査メタデータを更新する一度限りの保守処理

通常利用する入口は次の3つ。

- `launchers/base-study.ps1`: 基本COMシミュレーションとインピーダンススイープ
- `launchers/hybrid-50ohm.ps1`: 50 Ω固定のDMS＋ラダー探索
- `launchers/stage2-study.ps1`: 構成・結線・インピーダンスの共同探索

`maintenance/` のスクリプトは通常の試行には使用しない。
