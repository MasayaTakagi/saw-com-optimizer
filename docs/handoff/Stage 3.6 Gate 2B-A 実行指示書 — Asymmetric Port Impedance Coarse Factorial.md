# Stage 3.6 Gate 2B-A 実行指示書
## Asymmetric Port Impedance Coarse Factorial

※前版からの変更点：  
Gate 2A closeout後に軽微なバグ修正が入ったため、旧Section 2の **`stage3.6-gate2a-closed` commitとの完全一致要求は撤廃**する。

---

# 2. Execution baseline

Gate 2B-Aは、**軽微なバグ修正を含む最新のcleanなmain**を開始点とする。

開始前に以下を記録すること。

```text
git status
git branch --show-current
git rev-parse HEAD
git log -5 --oneline
```

期待状態：

```text
branch = main
working tree = clean
```

`stage3.6-gate2a-closed` tagとのHEAD一致は要求しない。

ただしreview bundleには、

```text
Gate 2A canonical tag:
stage3.6-gate2a-closed

Gate 2B-A actual starting commit:
<current HEAD>
```

を記録する。

## Bugfix impact check

Gate 2A closeout後の変更について、簡潔に差分を確認し、

```text
- infrastructure / test / reporting only
- numerical path affected
```

のどちらかを記録する。

軽微な修正であり、optimizer・COM計算・objective・constraint・port termination計算に影響しないことが確認できれば、**Gate 2Aの科学的判定を再オープンしない**。

一方、数値計算経路に影響する修正だった場合は、Gate 2B-Aの `50/50 Ω × 3 seeds × 16k` を必ず新しいコードで再実行し、controlとして扱う。

---

# 3. 作業branch

最新のcleanなmainから、

```text
stage3.6-gate2b-a-asymmetric-impedance
```

を作成する。

既存のWIP branchをbaseにしない。

---

# 4. 今回の目的

Gate 2Aで確定したDMS production search spaceを固定したまま、

```text
Zin
Zout
```

を独立に変更し、DMS性能に対するport impedance sensitivityを評価する。

確認する問い：

1. `Zin` の主効果
2. `Zout` の主効果
3. `Zin × Zout` interaction
4. 左右非対称DMSにおけるimpedance responseの非対称性

特に、

```text
25/50 vs 50/25
25/100 vs 100/25
50/100 vs 100/50
```

をpairedに比較する。

---

# 5. 固定条件

以下はGate 2Aから変更しない。

```text
DMS topology
search space = G1 + G2

optimizer algorithm
optimizer protocol
objective definition
constraint definition
frequency grid
COM model
material / COM parameters
parameter bounds other than port impedance
```

今回追加する実験変数は、

```text
Zin
Zout
```

のみ。

---

# 6. 禁止するDOF追加

```text
G3 / center aperture
additional geometric asymmetry
material optimization
COM coefficient optimization
ladder resonator
Hybrid topology
complex external impedance
frequency-dependent external impedance
```

を追加しない。

Port impedanceはpure real resistanceのみ。

---

# 7. 3×3 factorial

以下の9条件をすべて実行する。

| ID | Zin | Zout |
|---|---:|---:|
| Z25_25 | 25 Ω | 25 Ω |
| Z25_50 | 25 Ω | 50 Ω |
| Z25_100 | 25 Ω | 100 Ω |
| Z50_25 | 50 Ω | 25 Ω |
| Z50_50 | 50 Ω | 50 Ω |
| Z50_100 | 50 Ω | 100 Ω |
| Z100_25 | 100 Ω | 25 Ω |
| Z100_50 | 100 Ω | 50 Ω |
| Z100_100 | 100 Ω | 100 Ω |

---

# 8. Evaluation budget

```text
16,000 evaluations / run
3 paired cold seeds
```

合計：

```text
9 conditions
× 3 seeds
× 16k
=
432,000 evaluations
```

同一の3 seedsを全conditionで使用する。

previous runのpopulation、best individual、checkpoint等を引き継がない。

---

# 9. Preflight

本実験前に、

```text
25/50
50/25
```

を使ってZin/Zoutがsimulation coreまで正しい順序で渡されていることを確認する。

確認対象：

```text
config
runner
network termination
COM / network evaluation interface
result metadata
```

smoke testはproduction結果へ混ぜない。

---

# 10. Primary / Secondary metrics

Primary:

```text
median max constraint violation
```

Secondary:

```text
sum constraint violation
objective

worst passband IL
passband ripple

input VSWR
output VSWR

stopband violation
individual constraint violations

seed dispersion
late improvement
runtime
termination status
```

---

# 11. 必須解析

## 11.1 50/50 comparison

全conditionを50/50とpaired比較する。

## 11.2 Transpose comparison

```text
25/50 vs 50/25
25/100 vs 100/25
50/100 vs 100/50
```

を同一seed同士で比較する。

## 11.3 Asymmetry

```text
Δasym(Z1,Z2)
=
M(Z1,Z2) - M(Z2,Z1)
```

を算出する。

## 11.4 Port sensitivity

```text
25/50
50/50
100/50
```

→ Zin sensitivity

```text
50/25
50/50
50/100
```

→ Zout sensitivity

## 11.5 Interaction

ZinとZoutの効果が単純加算で説明できるか、interactionが存在するか確認する。

---

# 12. Heatmap

最低限、

```text
median max constraint violation
median sum constraint violation
median objective
```

について3×3 heatmapを作成する。

軸：

```text
x = Zout
y = Zin
```

で統一する。

---

# 13. Gate 2B-A終了条件

以下が完了した時点で停止する。

```text
9 conditions complete
3 paired seeds complete
16k complete

aggregate tables
paired comparisons
transpose comparisons
asymmetry analysis
port sensitivity analysis
interaction assessment
heatmaps
convergence summary
tests
review bundle
```

その後、

```text
DO NOT START GATE 2B-B
DO NOT RUN 32k
DO NOT RUN 64k
DO NOT MODIFY TOPOLOGY
```

ChatGPT reviewを待つ。

---

# 14. Review bundle

```text
stage3_6_gate2b_a_asymmetric_impedance_review.zip
```

最低限：

```text
stage3_6_gate2b_a_summary.md

experiment_matrix.csv
all_seed_results.csv
condition_summary.csv

paired_vs_50ohm.csv
transpose_pair_comparison.csv
asymmetry_summary.csv
convergence_summary.csv

heatmap_max_violation.png
heatmap_sum_violation.png
heatmap_objective.png

test_summary.md

git_status.txt
git_log.txt
baseline_diff_summary.md

reproduction / config metadata
```

`baseline_diff_summary.md`には、

```text
stage3.6-gate2a-closed
→
Gate 2B-A starting HEAD
```

の変更概要と、数値結果への影響有無を記載する。

---

# 15. 最終handoff

完了後、

```text
stage3_6_gate2b_a_asymmetric_impedance_review.zip
```

を作成して停止する。

**Gate 2B-Bへ自動進行しないこと。**