# 設定ファイル構成

- `models/`: COM材料・デバイス係数。現在は仮定数のみ。
- `base/`: 帯域仕様、製造制約、基本最適化条件。
- `studies/`: 個別試行のインピーダンス、構成、結線、探索予算。

試行設定の `base_config`、基本設定の `com_file` は、それぞれのYAMLからの相対パスで指定する。

短時間確認には `studies/stage2_pilot.yaml`、本探索には `studies/stage2_full.yaml` を使用する。
