# Stage 3.6 Gate 2B-B 作業指示書
## Asymmetric Impedance Local Refinement

### 0. 目的
Stage 3.6 Gate 2B-A の coarse scan 結果を受けて、50–100 Ω 領域で局所 refinement を実施する。

本 Gate の目的は以下の4点である。

1. `50/50 Ω` と `100/100 Ω` のどちらがより有望な basin かを確認する。
2. 50→100 Ω の対角線上に、より良い中間インピーダンスが存在するか確認する。
3. `Zin != Zout` の非対称ポートインピーダンスが、対称条件を上回る可能性があるか確認する。
4. Gate 2B-A の 16k coarse scan で見えた順位・interaction・transpose asymmetry が、32k budget でも再現するか確認する。

**この Gate では最終インピーダンスを確定しない。**
目的は、Gate 2B-C 以降で高予算確認すべき候補領域を絞り込むことである。

---

## 1. 前提・固定事項

Gate 2B-A との比較可能性を維持するため、以下を固定すること。

- optimizer: 現行 production optimizer
- SAW topology: 現在の DMS 単体構成
- objective / constraint 定義: Gate 2B-A と同一
- validation grid: Gate 2B-A と同一
- parameter bounds: Gate 2B-A と同一
- convergence 判定: Gate 2B-A と同一
- cold start
- seed set: Gate 2B-A と同一3 seed
- 各条件で独立最適化を行う
- 前条件の best design を次条件へ warm-start してはならない

**禁止事項**

- 本 Gate 中に optimizer algorithm を変更しない
- 本 Gate 中に探索 DOF を追加・削除しない
- parameter bounds を拡張・縮小しない
- objective / constraint weight を変更しない
- validation grid を変更しない
- Gate 2B-A の best design を初期値として流用しない
- 実験途中の結果を見て任意に条件を追加・削除しない

必要な変更が見つかった場合は、実験を改変せず issue / note として記録すること。

---

## 2. 実験マトリクス

以下の9条件を実行する。

| Condition | Zin [Ω] | Zout [Ω] | Role |
|---|---:|---:|---|
| B1 | 50.0 | 50.0 | Gate 2B-A reference |
| B2 | 62.5 | 62.5 | diagonal refinement |
| B3 | 75.0 | 75.0 | diagonal midpoint |
| B4 | 87.5 | 87.5 | diagonal refinement |
| B5 | 100.0 | 100.0 | Gate 2B-A high-Z candidate |
| B6 | 50.0 | 75.0 | asymmetric transpose pair A |
| B7 | 75.0 | 50.0 | asymmetric transpose pair A |
| B8 | 75.0 | 100.0 | asymmetric transpose pair B |
| B9 | 100.0 | 75.0 | asymmetric transpose pair B |

25 Ω側は Gate 2B-A で primary metric が明確に劣っていたため、Gate 2B-B では追加探索しない。

---

## 3. Optimizer 実行条件

各 impedance condition について以下で実行する。

- budget: **32,000 unique evaluations / run**
- seeds: **3**
- seed IDs: Gate 2B-A と同一
- start mode: cold start
- total runs: **27**
- total nominal evaluations: **864,000**

各 run では以下を必ず保存する。

- unique evaluation count
- best-so-far history
- best design parameters
- objective
- max constraint violation
- per-constraint violation
- feasible / infeasible
- active limiting constraint
- convergence status
- last meaningful improvement evaluation
- runtime
- random seed
- Zin
- Zout

---

## 4. 実行前 preflight

本計算前に以下を確認すること。

### 4.1 impedance propagation
少なくとも以下の2ケースで Zin / Zout が評価系まで正しく伝搬していることを確認する。

- `Zin=50, Zout=75`
- `Zin=75, Zout=50`

左右を入れ替えたときに同一値へ潰れていないことを確認する。

### 4.2 budget
1 run あたり `32,000 unique evaluations` が正しく設定されていること。

### 4.3 seed
Gate 2B-A と同一の3 seed を使用していること。

### 4.4 cold start
各 condition / seed が独立初期化されていること。

### 4.5 validation grid
Gate 2B-A と同一 grid であることを metadata に記録する。

preflight に失敗した場合、本実験を開始せず修正すること。

---

## 5. Primary metric

主評価指標は Gate 2B-A と同様に、

**median max constraint violation across 3 seeds**

とする。

ただし、median の大小だけで最終判断してはならない。

条件ごとに最低限以下を集計する。

- median max constraint violation
- mean max constraint violation
- min
- max
- standard deviation
- seed-wise values
- feasible count / 3
- median objective
- active limiting constraint distribution
- convergence count / 3

---

## 6. 必須解析

### 6.1 Diagonal impedance profile

以下の系列を比較する。

`50/50 -> 62.5/62.5 -> 75/75 -> 87.5/87.5 -> 100/100`

目的:

- 単調傾向の確認
- 中間 optimum の有無
- flat basin の有無
- 50 Ω basin と 100 Ω basin が連続か別 branch かの兆候確認

最低限以下を可視化する。

- median max violation vs diagonal impedance
- seed-wise scatter
- error range

---

### 6.2 Transpose analysis

以下の transpose pair を paired comparison する。

- `50/75 <-> 75/50`
- `75/100 <-> 100/75`

seed ごとに、

`Delta_transpose = V(Zin, Zout) - V(Zout, Zin)`

を計算する。

確認項目:

- 3 seed で符号が一致するか
- median difference
- difference magnitude
- Gate 2B-A と左右非対称傾向が整合するか

---

### 6.3 Interaction analysis

75 Ω付近を中心に Zin / Zout interaction を評価する。

対象:

- 50/75
- 75/50
- 75/75
- 75/100
- 100/75

Gate 2B-A では、片側のみ 100 Ωに変更すると悪化する一方、100/100 では改善するという interaction が観測された。

この傾向が Gate 2B-B でも維持されるかを確認する。

**Zin と Zout を独立な1次元問題として扱わないこと。**

---

### 6.4 Convergence analysis

各 run の best-so-far history を解析し、最低限以下の evaluation point で best metric を保存する。

- 16k
- 24k
- 28k
- 32k

以下を計算する。

`Delta_16k_32k = V_16k - V_32k`

追加で、

- last meaningful improvement evaluation
- last meaningful improvement / total budget
- 90% budget 以降の improvement 有無
- 95% budget 以降の improvement 有無

を集計する。

目的は、32k が比較用 budget として十分か判定することである。

---

### 6.5 Boundary-hit analysis

Gate 2B-A では一部 best design が parameter bounds に張り付いていた。

特に注意する項目:

- `io_idt_pairs`
- `reflector_electrodes`
- `aperture`
- その他 bound 到達パラメータ

各 best design について、

- lower bound hit
- upper bound hit
- normalized distance to nearest bound

を保存する。

**ただし本 Gate 中に bounds は変更しない。**

boundary hit は Gate 2B-C / 後続 DOF 検討の判断材料としてのみ使用する。

---

### 6.6 Constraint bottleneck analysis

各 run について最大違反を支配する constraint を特定する。

集計例:

- stop_1
- stop_2
- insertion loss
- input VSWR
- output VSWR
- その他

Gate 2B-A では stop_1 が主要 bottleneck だったため、32k でも同傾向か確認する。

---

## 7. Gate 2B-B の判断ロジック

### Case A: 対角線上に明確な候補 basin が現れる

例:

- 75/75
- 87.5/87.5

などが複数 seed で 50/50 および 100/100 より安定して良好。

→ Gate 2B-C でその近傍を高 budget refinement する候補とする。

---

### Case B: 50/50 と 100/100 が依然としてほぼ同等

condition difference が seed variation と同程度以下。

→ Gate 2B-C では条件数を絞り、

- 50/50
- 中間候補
- 100/100

を中心に **64k × 5 seeds 等**の statistical confirmation を検討する。

**この判断は Gate 2B-B 結果レビュー後に行う。自動では実行しない。**

---

### Case C: 非対称条件が対称条件を明確に上回る

例えば `75/100` または `100/75` が対応する対称条件より複数 seed で改善。

→ Gate 2B-C で asymmetric local 2D refinement を候補とする。

---

### Case D: 32k でも late improvement が支配的

多数の run が budget 90–95%以降まで有意改善を続ける場合。

→ impedance grid をさらに細かくする前に optimizer budget / convergence を再評価する。

---

## 8. Feasibility の扱い

Gate 2B-B の PASS 条件を「feasible 解の獲得」としてはならない。

Gate 2B-B の主目的は impedance 条件間の相対比較である。

ただし feasible 解が出た場合は別途重要イベントとして記録する。

feasible 出現時には以下を保存する。

- condition
- seed
- first feasible evaluation
- final feasible objective
- final max violation
- design parameters

---

## 9. 必須成果物

実験完了後、review bundle に最低限以下を含めること。

### CSV / structured output

- `all_seed_results.csv`
- `condition_summary.csv`
- `paired_comparison.csv`
- `transpose_analysis.csv`
- `interaction_analysis.csv`
- `convergence_summary.csv`
- `boundary_hit_summary.csv`
- `constraint_bottleneck_summary.csv`

### Markdown

- `gate2b_b_final_summary.md`
- `test_summary.md`
- `reproduction_metadata.json` または同等の reproducibility metadata

### Plots

最低限以下を作成する。

1. diagonal impedance profile
2. Zin/Zout result map / heatmap
3. seed-wise scatter
4. convergence curves
5. transpose comparison
6. boundary-hit visualization

---

## 10. Final summary に必ず記載する内容

`gate2b_b_final_summary.md` には最低限以下を記載する。

1. 実験条件
2. 全 run 完走数
3. failed run 数
4. feasible run 数
5. 各 impedance condition の primary metric
6. 50/50・75/75・100/100 の比較
7. diagonal trend
8. transpose asymmetry
9. interaction
10. convergence status
11. late-improvement ratio
12. active constraint distribution
13. boundary hits
14. Gate 2B-A との整合性
15. Gate 2B-C 候補
16. unresolved issues
17. 次段へ進めるかどうかの機械的な事実整理

**最終的な Gate 2B-C 実験条件はここで勝手に確定しないこと。**
ChatGPT レビューを挟んでから決定する。

---

## 11. 停止点

Gate 2B-B の全27 run と解析・成果物生成が完了したら、

**そこで停止すること。**

Gate 2B-C、
64k run、
5-seed confirmation、
parameter-bound expansion、
hybrid topology 実装

には進まない。

最終出力で明示的に、

`STAGE3_6_GATE2B_B_COMPLETE_STOP`

と記載すること。

---

## 12. 成功条件

Gate 2B-B は以下を満たせば完了とする。

- 9 conditions × 3 seeds が計画通り実行されている
- 各 run が 32k unique evaluations に到達、または失敗理由が明確
- common validation grid を使用
- diagonal / transpose / interaction / convergence / boundary analysis が完了
- Gate 2B-A との比較が可能
- review bundle が生成されている
- Gate 2B-C を自動実行せず停止している

feasible 解の有無や特定 impedance の勝敗は、完了条件ではない。

---

## 13. 実行方針の要約

この Gate では、

- 広く探さない
- 50–100 Ωに集中する
- Zin / Zout を joint problem として扱う
- 32k で再現性と convergence を確認する
- DOF / bounds / optimizer は変更しない
- 次 Gate には自動で進まない

ことを最優先する。
