# Stage 1/2 実装・検証記録

## 実装範囲

`CODEX_TASK.md` と `CODEX_STAGE2_TASK.md` を要求仕様として読み、2つの handoff ディレクトリは参照実装として差分を統合した。

- COM有限区間は符号規約を維持し、ゼロ近傍の entire function、スカラー/周波数配列パラメータ、真のgapの結合強制ゼロ、入力検証を追加した。
- 音響連立方程式は正規化残差を常時計算する。`simulate_filter(..., debug_diagnostics=True)` のときだけ、周波数ごとの条件数と最悪周波数を追加する。
- 電気2ポートは任意の正実数 `rs` / `rl` に対応し、受動性と相反性を絶対・相対許容差で検証する。
- 校正済みCOM providerはメタデータ検証までの枠だけを用意し、実測/FEMデータがない状態で係数を生成しない。
- DMSと直列/並列ラダー共振子を組み合わせた13構成、3種類のDMS結線を扱う。
- 整数設計変数は評価前に正規化してキャッシュキーと一致させ、変数数に応じて母集団を増やす。
- 粗い探索グリッドと密な合否判定の差を適応周波数交換で閉じる。
- topology × wiringを組として低・中・仕上げ予算のsuccessive halvingを行う。
- 各インピーダンスを独立探索した後、隣接インピーダンスの候補をwarm startとして同一予算で再探索する。再探索が悪化した場合は独立探索側を保持する。
- 50 Ω最良形状を固定して終端だけ変えたloading-only control、固定構成曲線、自由構成envelopeを別々に出力する。
- 目的関数と最終順位はともに、可否、最大仕様違反、違反合計、挿入損失の順で比較する。
- Stage 3 では wiring ごとの cold-seed集約順位、cutoff不確実性、任意のwinner/runner-up cold confirmationを使える。

主な実装入口は `src/sawopt/optimization/stage2_study.py`、レポートは `src/sawopt/reporting/stage2_report.py`、設定は `configs/studies/stage2_pilot.yaml` と `configs/studies/stage2_full.yaml`。

## 数値回帰とテスト

旧スカラーCOM計算との401周波数点比較では、P行列の最大絶対差は `7.580880525408319e-16`、旧結果ピークに対する相対差は `7.851031700365645e-16` だった。

`python -m unittest discover -s tests -v` は33件すべて成功した。解析極限、gap、区間分割同一性、相反性、受動性、任意終端、整数キャッシュ、適応周波数交換、母集団拡張、joint screening、隣接warm start、CLIおよびレポートに加え、Stage 3 のVSWR細分化、common validation、増分周波数キャッシュ、parity、seed集約を含む。

小予算ベンチマークでは、粗グリッドのみと同じ総評価回数で適応交換を使った9ケースの密グリッド挿入損失差は平均 `-0.30994 dB` だった。13変数の `P_D_P` では母集団7の最良最大仕様違反 `2.94420` に対し、母集団13では `2.69378` だった。これは探索機構の診断であり、統計的な性能主張ではない。記録は `runs/stage2-validation/summary.json` に保存した。

## パイロット結果

20/50/100 Ω、`D` / `P_D` / `P_D_P`、3結線、3シードで小規模パイロットを実行した。

| 終端 | 選択構成 | 結線 | worst IL | 最大仕様違反 | 50 Ω形状のloading-only IL |
|---:|---|---|---:|---:|---:|
| 20 Ω | P_D_P | center_outer_same | 9.3670 dB | 2.1223 | 10.8352 dB |
| 50 Ω | P_D | center_outer_same | 8.4666 dB | 1.8222 | 8.4666 dB |
| 100 Ω | P_D_P | center_outer_same | 9.5004 dB | 2.6397 | 10.3333 dB |

全点が仕様未達であり、低予算のパイロットから「50 Ωが最良」などの結論は出せない。本比較には仮COM定数しか使っていないため、実機設計の判断には校正データと本探索予算が必要になる。

## 出力

`runs/stage2-pilot-v1` に次を保存した。

- `report.html`: 集約レポート
- `impedance_envelope.csv`: 各インピーダンスの自由構成envelope
- `fixed_family.csv`: 構成・結線を固定した比較
- `impedance_summary.png`: IL、VSWR、リップル、面積、電極数など
- `stopbands.png`: 阻止帯域ごとの減衰量
- `loading_control.json` と `loading_control__*.npz`: 50 Ω形状固定の終端依存
- 各trialのJSON、JSONL、NPZ、checkpoint: 設計、履歴、応答、再開情報
- `manifest.json`: 設定スナップショット、依存版、ソース指紋、後処理変更履歴

## 制約

COM定数は `com_params_hypothetical.yaml` の仮値で、周波数・寸法依存の校正モデルではない。単一モード、固定材料、寄生回路なしのモデルであり、FEM/実測との一致は未検証。本探索設定は11インピーダンス × 13構成 × 3結線 × 3シードと大きいため、実行前に計算予算を確認する。
