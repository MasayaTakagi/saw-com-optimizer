# 設定ファイル構成

- `models/`: COM材料・デバイス係数。現在は仮定数のみ。
- `base/`: 帯域仕様、製造制約、基本最適化条件。
- `studies/`: current DMS topology and hybrid study configurations.
- `reference/`: immutable numerical inputs used by the current DMS topology study.

試行設定の `base_config`、基本設定の `com_file` は、それぞれのYAMLからの相対パスで指定する。

Run the current DMS topology study with `studies/dms_topology_screening.yaml`.
The separate 50 Ω hybrid workflow uses `studies/hybrid_50ohm.yaml`.
