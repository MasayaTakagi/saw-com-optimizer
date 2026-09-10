# 次期実験計画 — 50 Ω DMS Production Convergence

## 1. 目的

Stage 3.3までの比較結果を踏まえ、7次元DMS問題では Legacy SciPy Differential Evolution（DE）を標準optimizerとして採用する。

本実験の目的は、50 Ω条件において

1. optimizerが十分に収束しているか
2. soft boundの制約が解を押さえていないか
3. wiringごとのDMS性能限界をどこまで信頼してよいか
4. 20〜200 Ω探索へ移る際の標準計算budgetをどの程度にすべきか

を判定することである。

本実験では新optimizerの開発は行わない。
主眼は「現在の安定版optimizerを十分に回し、収束証拠を取得すること」に置く。

---

# 2. 固定する基本方針

## Optimizer

標準optimizer:

```text
Legacy SciPy Differential Evolution
```

L-SHADEは今回の本番には使用しない。

理由:

- 4000 unique evaluations × 5 cold seeds の公平なA/BでLegacy DEがわずかに優位
- best / median / seed IQR / basin hit / wall timeのいずれもLegacy DEが有利
- 7次元DMSではLegacy DEで十分競争力がある
- L-SHADEは将来の10D〜13D以上の高次元問題で再評価する

---

## 共通optimizer機能

以下は維持する。

```text
Legacy DE
+
feasibility-first ranking
+
adaptive frequency grid
+
common dense validation
+
incremental frequency evaluation
+
auto soft-bound expansion
+
integer neighborhood refinement
+
micro-polish
+
cold multi-seed
+
convergence certificate
```

---

# 3. 対象条件

## Port impedance

```text
Rs = 50 Ω
Rl = 50 Ω
```

本実験では50 Ωのみとする。

---

## DMS wiring

最低限、以下2条件を独立に評価する。

```text
center_outer_same
outer_ports
```

両者は別の電気的wiring条件であり、形状自由度共有の意味ではない。

---

## Seeds

```text
5 cold seeds
```

Stage 3.xで使用してきたseed集合を原則維持し、比較可能性を保つ。

---

## Parallel execution

```text
5 processes
```

原則として1 seed = 1 process。

各process内ではBLAS内部並列を抑制する。

推奨:

```text
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
```

worker数は過去の実SAW benchmarkで5 workersが有効だったため5を標準とする。

---

# 4. Evaluation budget

同一seed内ではcold restartせず、継続trajectoryとして実行する。

```text
500
 ↓
1000
 ↓
2000
 ↓
4000
 ↓
8000
 ↓
必要なら16000
```

budgetの定義は

```text
unique decoded design evaluations
```

とする。

単なる`maxiter`はbudget基準として使用しない。

各checkpointでrequested budgetの98%以上を消化していない場合は、そのcheckpointを有効な収束判定に使用しない。

---

# 5. Auto-bound policy

## 原則

```text
auto expand only
```

自動縮小は行わない。

---

## Soft / hard bounds

各変数について、

```text
initial/soft bound
hard bound
expandable
```

を明示する。

optimizerはsoft boundのみ変更可能。

hard boundは絶対に越えない。

---

## 特に注視する変数

過去実験で境界圧力が確認されたため、

```text
io_idt_pairs
center_idt_pairs
```

を重点監視する。

例:

```text
io_idt_pairs
20 → 15 → 10 → hard lower limit 8
```

必要に応じて段階的に拡張する。

---

## Integer boundary zone

整数変数ではlower boundそのものだけでなく、

```text
lower_bound
lower_bound + 1
```

をboundary zoneとして扱う。

例:

```text
bound = 15
15, 16 → lower-bound zone
```

---

## Boundary expansion trigger

通常ルート:

```text
複数seedでboundary pressure
        ↓
boundary probe
        ↓
改善方向が再現
        ↓
soft bound拡張
```

補助ルート:

```text
global bestがboundary zone
+
他seedより明確に良い
        ↓
elite boundary probe
```

1 seedのみの結果で即boundを変更しない。
ただし1 seedのみでも調査は許可する。

---

## Bound expansion後

bound変更時:

```text
design_space_version += 1
```

収束plateau履歴はリセットする。

ただしoptimizer trajectoryそのものは破棄しない。

既存populationを維持しつつ、10〜25%程度を新しく開いた領域へinjectする。

---

# 6. Frequency evaluation

## Search grid

optimizer中はadaptive frequency gridを使用する。

ただし、

```text
frequency grid converged
```

と

```text
design optimization converged
```

は別状態として扱う。

critical frequencyが追加されなくてもdesign budgetが残っていれば同じgrid上で探索を継続する。

---

## Common dense validation

checkpointおよびterminal candidateの比較は共通gridで行う。

最終結果比較用gridは最低限、

```text
base dense validation grid
+
全seedのcritical frequencies
```

のunionとする。

wiring内の全候補を同じvalidation gridで評価する。

---

# 7. Local refinement

## Integer refinement

Global DE終了後:

```text
finger pairs ±1 / ±2
reflector count ±1 / ±2
```

等の限定的な整数近傍探索を実施する。

全組み合わせ総当たりは避ける。

---

## Micro-polish

収束診断では

```text
best_candidate_polish_improvement
median_candidate_polish_improvement
```

を分離して保存する。

収束gateに使用するのはbest candidate側を基本とする。

本番最終候補では改善が確認されたpolished designを正式候補として採用してよい。

---

# 8. Convergence 判定

## Primary metric

仕様未達時:

```text
max_violation
```

を主指標とする。

仕様達成後:

```text
worst passband IL
```

を主指標とする。

---

## 必須観測値

各budget / seedについて以下を保存する。

```text
primary metric
max_violation
sum_violation
worst IL
all individual violations
feasible / infeasible
best-so-far trace
last significant improvement eval
validation gap
micro-polish improvement
boundary status
design_space_version
actual unique evaluations
solved frequency points
wall time
```

---

## Paired budget comparison

同じseedの連続budget間を比較する。

例:

```text
seed A: 2000 → 4000
seed B: 2000 → 4000
...
```

保存する統計:

```text
median improvement
IQR
max improvement
fraction of seeds with significant improvement
```

---

## Converged候補条件

同一design-space version内で、

1. 連続2 budget intervalでprimary metric改善が小さい
2. seed IQRが十分小さい
3. best candidate micro-polish改善が小さい
4. validation gapが十分小さい
5. budget後半で有意なbest更新がない
6. soft-bound pressureがない

を満たすこと。

初期目安:

```text
paired median primary improvement < 1〜2%
seed IQR < 0.1 primary-metric equivalent
best polish improvement < 0.02
validation gap < 0.02
last significant improvement < budgetの75%程度
```

閾値はレポートに明記し、隠れたmagic numberにしない。

---

# 9. Status分類

各wiringの最終statusは少なくとも以下とする。

```text
converged
likely_underoptimized
hard_bound_limited
inconclusive
```

意味:

### converged

optimizer・validation・soft boundsの観点から十分plateau。

### likely_underoptimized

budget増加またはlate improvementでまだ改善が継続。

### hard_bound_limited

optimizerはhard boundに押されており、現design space内での限界。

### inconclusive

design-space変更後のcheckpoint不足などで判定不能。

---

# 10. 実験フェーズ

## Phase A — 実装状態確認

新機能は原則追加しない。

以下のみ確認する。

```text
Legacy DE selected
5-process production enabled
auto-bound enabled
500→...→16000 continuation enabled
common validation enabled
review-bundle generation enabled
```

変更が必要な場合は局所patchのみ。

---

## Phase B — Automated preflight

本番前に短い自動preflightを実行する。

必須:

```text
unit tests
regression tests
budget accounting
checkpoint continuation
parallel parity
common validation parity
source hash freeze
review bundle smoke
```

optimizerコアに変更がなければ、人手のpre-production reviewは原則省略可能。

preflight FAIL時のみ停止する。

---

## Phase C — 50 Ω production

### center_outer_same

優先して実行。

```text
5 cold seeds
5 processes
500→1000→2000→4000→8000
必要なら16000
auto-bound ON
```

その後outer_portsを同じ条件で実行。

両wiringを同時5×2=10 processで走らせる必要はない。
1 wiringあたり5 processを使用し、CPU/RAM競合を避ける。

---

## Phase D — Automatic escalation

各checkpointで収束判定する。

例:

```text
4000で未収束
→ 8000へ継続

8000で未収束
→ 16000へ継続
```

ただしbound expansionが起きた場合はdesign-space versionが変わるため、旧versionのplateau証拠をリセットする。

---

## Phase E — Review bundle

本番終了後、1コマンドでreview bundleを生成する。

最低限含める:

```text
repo snapshot
source hash
git diff/status
exact config
COM parameter input
environment versions
full test logs
run manifest
all seed summaries
checkpoint summaries
boundary events
design-space versions
best designs
common-grid metrics
paired-budget statistics
parallel timing
wall-clock timing
convergence decision
```

bundleは展開直後にself-containedでテスト再実行可能とする。

---

# 11. Token-efficient Codex execution

長時間production中にCodexが頻繁なpollingを行わない。

標準運用:

```text
Codex
 ↓
preflight開始
 ↓
PASSならproductionを1コマンド起動
 ↓
Python内部で
   seed並列
   checkpoint
   auto-bound
   convergence
   escalation
   bundle generation
 ↓
終了
 ↓
Codexがbundleを確認
```

途中監視は異常時を除き最小限とする。

プロセス中断時はcheckpointから再開する。

---

# 12. 実験終了後の判断

## Case A — 仕様達成

50 Ω DMSで仕様達成した場合:

- geometryとwiringを記録
- optimizer convergenceを確認
- Phase 2の20〜200 Ω探索へ進む

---

## Case B — 収束したが仕様未達

soft bound pressureなし、
seed間収束、
budget plateau、
polish改善なしなら、

```text
現在の仮COMモデル
+
現在のDMS構造
+
当該wiring
```

における性能限界の強い証拠とする。

その後20〜200 Ω探索へ進み、
50 Ωが本当に最適なloadingかを比較する。

---

## Case C — hard-bound limited

hard physical/manufacturing boundへ押されている場合:

```text
optimizer限界
```

ではなく、

```text
design-space / manufacturing constraint limit
```

として扱う。

hard boundの物理妥当性を別途レビューする。

---

## Case D — 16000でもunderoptimized

16000でも

```text
large paired improvement
large seed spread
late improvement
```

が残る場合は、7D DMSでもLegacy DE探索が不十分。

この場合のみoptimizer戦略を再検討する。

候補:

```text
L-SHADE再評価
island DE
larger population
alternative mutation strategy
```

ただし実測根拠なしに先行導入しない。

---

# 13. Phase 2へ進む条件

50 Ωについて最低限、

```text
converged
または
hard_bound_limited
```

を得る。

その結果から、

```text
standard unique evaluation budget
```

を決定する。

例:

```text
50 Ωで8000で十分
→ 20〜200 Ωの初期標準budget = 8000 / seed
```

ただし10D/13D hybridでは次元に応じて別途再スケールする。

---

# 14. 次期フェーズ予告

50 Ω完了後:

```text
Phase 2:
20〜200 Ω DMS impedance sweep
```

各Zについて構造を独立に再最適化する。

同時に、

```text
50 Ω最適geometryを固定してloadingだけ変更
```

するcontrolを残し、

```text
loading effect
vs
re-optimization effect
```

を分離する。

---

# 15. 今回やらないこと

以下は本実験では実施しない。

```text
L-SHADE追加改良
CMA-ES導入
Bayesian optimization
surrogate model
GPU化
Numba/JIT最適化
COM physics変更
center/outer独立geometry追加
hybrid topology sweep
20〜200 Ω sweep
```

これらは50 Ω DMS convergence完了後に再検討する。

---

# 16. 成果物

本実験終了時に必要な成果物:

```text
1. 50 Ω center_outer_same convergence report
2. 50 Ω outer_ports convergence report
3. all checkpoint/seed CSV
4. paired-budget comparison
5. boundary expansion history
6. final design-space bounds
7. best geometry per wiring
8. common dense response data
9. convergence certificate
10. total / per-seed wall time
11. full test logs
12. self-contained review bundle ZIP
```

---

# 17. 最終目標

この実験の目的は、

> 「50 Ωで最良の値を1個見つけること」

ではない。

目的は、

> **現在のoptimizerとdesign spaceで、50 Ω DMSをどこまで最適化できたかを定量的に証明すること**

である。

この証拠を基準として、次の20〜200 Ω再最適化結果を公平に比較する。
