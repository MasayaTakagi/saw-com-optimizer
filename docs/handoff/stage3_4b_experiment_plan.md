# Stage 3.4b 実験計画 — 50 Ω `center_outer_same` 収束証明強化

## 1. 目的

Stage 3.4 では `io_idt_pairs` の下限回復が 20 → 15 → 10 まで機能し、32k で seed 間 IQR も大幅に縮小した。一方で、32k まで到達しても一部 seed が遅く改善し、最終 checkpoint で境界圧力・stagnation recovery・frequency-grid 更新が残ったため、50 Ω `center_outer_same` の探索が十分に収束したとはまだ証明できない。

Stage 3.4b の目的は、50 Ω `center_outer_same` について「探索予算不足」「seed 数不足」「人工的な `io_idt_pairs=10` 下限」「収束判定の弱さ」を同時に解消し、次段の impedance sweep に進めるだけの production-grade convergence certificate を作ることである。

本実験ではフィルタ仕様そのものを変更しない。COM/network モデル、目的関数、トポロジー、50 Ω 条件は固定する。

---

## 2. 実行環境と並列化方針

ローカル実行環境を基準とする。

- CPU: AMD Ryzen 7 PRO 4750G
- 8 physical cores / 16 logical threads
- RAM: 約 16 GB
- OS: Windows

production の基本設定は以下とする。

```yaml
optimizer_validation:
  parallel:
    seed_level: true
    production_workers: 8
    blas_threads_per_worker: 1
```

論理 16 thread を最初から 16 worker で埋めない。今回の workload は seed ごとの独立 CPU process が中心なので、まず 8 physical cores = 8 workers を標準とする。

本番前に 8 seed を使い、`benchmark_workers: [4, 6, 8]` で短い throughput benchmark を行う。benchmark は optimizer startup overhead の影響を小さくするため、現行 100 evaluations より増やし、原則 500–1000 unique designs/seed とする。

記録する情報は wall time、unique evaluations/sec、CPU 情報、logical/physical core 数、total/available RAM、worker 数、BLAS thread 数とする。可能なら process peak RSS も記録する。8 workers で RAM 圧迫または throughput 悪化が見られた場合のみ 6 workers へ下げる。

---

## 3. Cold seed 方針

### Main run

Stage 3.4 の既存 5 seed を維持し、3 seed を追加して合計 8 cold seeds とする。

```yaml
seeds:
  - 20260909
  - 20260910
  - 20260911
  - 20260912
  - 20260913
  - 20260914
  - 20260915
  - 20260916
```

8 seed は 8 physical cores と一致し、5 seed より seed distribution / boundary vote / improvement fraction の分解能を上げられる。

### Conditional confirmation

同一 run の途中で seed 数を 8 → 16 に増やす実装は行わない。boundary pressure や design-space version が全 seed で同期している現在の continuation coordinator を複雑化し、収束証明を読みにくくするためである。

8 seed run 終了後、seed-related gate だけが曖昧な場合に限り、Stage 3.4c として追加 8 cold seeds（20260917–20260924）を使う confirmatory run を実施する。これは Stage 3.4b の結果を見て決定する。

---

## 4. Design-space 方針

Stage 3.4 の最終 5 seed は `io_idt_pairs = 10,10,10,10,11` で、5/5 が lower-bound zone に入った。一方、既存 `boundary_probe()` は対象変数だけを変更して他変数を固定する coordinate probe であり、`io_idt_pairs=8` の領域を full re-optimization した結果ではない。

Stage 3.4b ではこの不確実性を消すため、`io_idt_pairs` の active lower bound を最初から hard lower bound である 8 に開く。

```yaml
optimizer_validation:
  bounds:
    io_idt_pairs:
      initial: [8, 100]
      hard: [8, 120]
      expandable: true
      lower_steps: []
```

これにより `[8,10)` を通常の optimizer が他変数と同時に探索できる。`io_idt_pairs` lower-bound probe に依存して「8 が不要」と判定する必要がなくなる。

`center_idt_pairs` 等、今回 boundary pressure が確認されていない変数は現行 Stage 3.4 の設定を維持する。

---

## 5. 探索 budget

64k を固定上限にはしない。Stage 3.4b は checkpoint ごとの収束判定で早期終了し、必要な場合のみ長い budget へ進む。

推奨 checkpoint:

```yaml
optimizer_validation:
  budgets:
    - 16000
    - 32000
    - 48000
    - 64000
    - 96000
    - 128000
    - 192000
    - 256000
    - 384000
  optional_max_budget: 512000
  auto_escalate: true
  minimum_convergence_budget: 32000
```

解釈:

- 16k–128k: normal region
- 192k–256k: extended region
- 384k–512k: emergency region
- 512k: absolute hard stop

512k まで必ず走らせるのではなく、convergence certificate が成立した checkpoint で即終了する。

512k checkpoint で新たな boundary event / stagnation recovery / unresolved grid update が発生した場合、無理に converged とせず `inconclusive_at_hard_ceiling` または `likely_underoptimized` として終了する。hard ceiling を超えて自動延長しない。

---

## 6. 収束判定の修正

Stage 3.4 では median plateau だけを見ると、2/5 seed が大幅改善していても plateau と判定できる問題があった。Stage 3.4b では以下を certificate gate に追加する。

### 6.1 Material-improvement seed fraction

各 paired budget interval について、既存の `fraction_seeds_improving_by_threshold` を実際の gate に使う。

infeasible case の初期案:

```yaml
convergence:
  infeasible:
    paired_median_primary_relative_improvement: 0.02
    paired_median_primary_absolute_improvement: 0.02
    max_fraction_seeds_materially_improving: 0.25
```

最後の 2 interval がとも、median plateau 条件を満たし、かつ materially improving seed が 25% 以下であることを要求する。8 seed なら最大 2/8 まで。

### 6.2 Worst-seed spread

IQR だけで worst seed が隠れないよう、最終 seed 群に以下を追加する。

```yaml
convergence:
  infeasible:
    final_seed_primary_iqr: 0.10
    final_seed_primary_worst_minus_median: 0.10
```

feasible case は IL 単位の対応 threshold を別に定義する。

### 6.3 Frequency-grid convergence

`grid_converged` を certificate gate に入れる。

初期基準:

```yaml
convergence:
  min_grid_converged_seed_fraction: 0.875
```

8 seed のうち最低 7 seed が grid-converged であることを要求する。加えて validation gap gate は維持する。

必要なら `max_validation_gap_primary` も併記し、median だけで 1 seed の大きな gap を隠さないようにする。

### 6.4 Pending recovery gate

stagnation recovery が現在の checkpoint で発火した場合、その checkpoint では convergence を認めない。必ず次の checkpoint で、refresh 後の population が実際に探索されたことを確認する。

実装上は、各 trajectory に `recovery_pending_confirmation` 相当の状態を持たせるか、coordinator 側で「current budget に recovery event がある場合は convergence stop 禁止」とする。

### 6.5 Pending boundary-confirmation gate

boundary pressure が初めて成立し、`required_persistent_checkpoints=2` の 1 回目になった checkpoint では convergence を認めない。

今回の 32k のように「最終 checkpoint で初めて 5/5 seed が boundary zone」に入って、そのまま停止することを防ぐ。

hard bound に既に達している変数については、未解決 pressure ではなく `hard_bound_reached` として明示的に解決済みにできるようにする。

### 6.6 Late improvement / polish / validation

既存の以下の gate は維持する。

- late improvement
- validation gap
- micro-polish improvement
- 2 consecutive plateau intervals
- feasible/infeasible consistency

---

## 7. Stagnation recovery 修正

現状は checkpoint 到達後に duplicate stagnation を検出し population を refresh するため、最終 checkpoint で発火すると refresh population が一度も探索されずに終了する。

Stage 3.4b では最低限、`recovery fired at current checkpoint => convergence stop forbidden` を実装する。

既存 recovery 条件はまず維持する。

```yaml
stagnation_recovery:
  enabled: true
  duplicate_fraction_threshold: 0.80
  minimum_interval_objective_calls: 500
  unique_evaluations_since_improvement: 2000
  max_recoveries_per_design_space_version: 2
```

Stage 3.4b の主目的は recovery trigger の再調整ではなく、「trigger した recovery を必ず次 interval で検証する」こととする。

---

## 8. 実験フェーズ

### Phase A — Preflight / parallel benchmark

目的はローカル 4750G 上で production workers を決めること。

実施内容:

1. 8 cold seeds、50 Ω、`center_outer_same`、固定小 budget。
2. worker count = 4, 6, 8 を比較。
3. BLAS threads = 1 固定。
4. throughput とメモリ余力を記録。
5. throughput が同等なら 8 workers を採用。8 workers で RAM pressure / severe contention があれば 6 workers。

Phase A は optimizer quality の比較には使わない。

### Phase B — Stage 3.4b main convergence run

8 cold seeds、`io_idt_pairs` lower bound = 8、最大 512k、早期停止ありで本番を実行する。

原則、すべての checkpoint で以下を保存する。

- search / validated primary metric per seed
- best design per seed
- paired interval deltas
- materially improving seed fraction
- IQR / median / worst / worst-minus-median
- validation gap median/max
- grid-converged seed fraction
- last significant improvement position
- boundary pressure / probe / expansion event
- stagnation duplicate fraction / recovery event
- active design-space version
- unique evaluations and objective calls
- wall time and resource metadata

### Phase C — Conditional confirmation only

Phase B が hard ceiling まで未収束、または主に seed consistency gate だけで判定が曖昧な場合のみ実施する。

追加 8 cold seeds を用い、Stage 3.4c として独立 run を作る。Phase B の途中に seed を追加して同一 certificate に混ぜない。

---

## 9. Stage 3.4b の合格条件

次の全条件を満たした場合のみ 50 Ω `center_outer_same` を `converged` とする。

1. 同一 design-space version で最低 3 checkpoints があり、最後の 2 paired intervals が plateau。
2. 最後の 2 intervals で materially improving seed fraction ≤ 25%。
3. final seed IQR が threshold 未満。
4. final worst-minus-median spread が threshold 未満。
5. late-improvement gate を全 seed が通過。
6. validation gap と micro-polish gate を通過。
7. grid-converged seed fraction ≥ 87.5%（8 seed 中 7 seed以上）。
8. current checkpoint に pending stagnation recovery がない。
9. current checkpoint に未確認の boundary pressure がない。
10. hard-bound-limited 状態が未解決でない。
11. budget accounting / source hash / tests / review bundle integrity が正常。

上記のうち一つでも満たさなければ `converged` にしない。

---

## 10. 判定後の次アクション

### A. 128k 以前で converged

Stage 3.4b 成功。50 Ω convergence methodology を固定し、20–200 Ω impedance sweep の設計へ進む。

### B. 192k–512k で converged

成功。ただし impedance sweep で全点に同 budget を与えると重いため、screening → promising impedance only deep certification の二段階方式を採用する。

### C. 512k でも late improvement / recovery / grid instability が残る

Legacy DE continuation の budget 追加だけでは効率が悪い可能性が高い。Stage 3.3 で計画していた optimizer A/B（例: LSHADE 系、CMA-ES/混合離散対応など）へ進む判断材料とする。

### D. 十分に converged するが max violation が ~0.7 前後で仕様から遠い

「50 Ω center_outer_same が現 optimizer で探索不足」という仮説を棄却し、現在の COM model / topology / design degrees of freedom では仕様達成が難しい可能性が高いと判断する。次に impedance sweep または topology comparison へ進む。

---

## 11. 実装対象

Stage 3.4b の前に最低限変更する対象:

- `sawopt/optimization/convergence_policy.py`
  - material-improvement seed fraction gate
  - worst-minus-median gate
  - grid-converged fraction gate
  - evidence 出力追加
- `sawopt/studies/continuation.py`
  - current-checkpoint recovery pending gate
  - boundary persistence pending gate
  - resource metadata / benchmark reporting の改善
  - best-candidate validated rank の生成順序修正
- Stage 3.4b config fragment
  - 8 seeds
  - workers 8
  - budget schedule ～512k
  - `io_idt_pairs.initial.lower = 8`
  - new convergence thresholds
- tests
  - 2/8 materially improving seeds の境界ケース
  - 3/8 improving なら fail
  - IQR pass でも worst-minus-median fail
  - grid convergence 6/8 fail, 7/8 pass
  - recovery fired at final checkpoint cannot converge
  - first boundary-pressure checkpoint cannot converge
  - next checkpoint after recovery can converge when all gates pass

既存の COM/network numerical core は変更しない。

---

## 12. Review bundle に必須の追加情報

次回 review bundle では、後からローカル資源と実験環境を混同しないように `environment/local_runtime.json` を追加し、最低限以下を記録する。

```json
{
  "cpu_model": "AMD Ryzen 7 PRO 4750G with Radeon Graphics",
  "physical_cores": 8,
  "logical_cores": 16,
  "ram_total_gib": 16,
  "production_workers": 8,
  "blas_threads_per_worker": 1,
  "platform": "Windows",
  "python_version": "..."
}
```

可能なら run start/end 時刻、wall time、peak aggregate worker RSS も保存する。

---

## 13. 実験名

推奨:

- experiment: `stage3_4b_extended_convergence`
- config: `next_50ohm_center_outer_same_stage34b.yaml`
- run: `runs/next_50ohm_center_outer_same_stage34b`

この Stage 3.4b を、50 Ω `center_outer_same` に対する最終 convergence certification run と位置づける。

---

# 14. Codex 実装指示書

以下は Stage 3.4b を実装・実行するための Codex 向け作業指示である。実装時は本節を最優先の実行仕様として扱うこと。既存コードの実際の API 名・config schema・モジュール分割が本書の記述と異なる場合、既存設計を尊重して最小差分で適合させる。**COM/network numerical core、目的関数の意味、50 Ω 条件、既存の設計仕様値は変更しない。**

## 14.1 作業開始前の必須確認

最初にコード変更をせず、以下を調査して簡潔な実装計画を出力すること。

1. 現在の Stage 3.4 config と continuation 実装を特定する。
2. `convergence_policy.py` または相当モジュールで、現在の convergence certificate がどの evidence を受け取り、どの gate を使っているか確認する。
3. checkpoint 後の処理順序を確認する。
   - optimize interval
   - validation
   - adaptive frequency-grid update
   - boundary pressure / probe / expansion
   - stagnation detection / recovery
   - convergence judgment
   - checkpoint serialization
4. `best_candidates.json` と review summary の生成箇所を確認する。
5. worker 並列化、BLAS thread 固定、benchmark 実装の現在位置を確認する。
6. source hash、run metadata、test status が review bundle にどう保存されているか確認する。

この確認時点で、既存テストを一度実行して baseline を保存する。baseline で失敗するテストがある場合は、Stage 3.4b の変更と混同せず明記する。

## 14.2 実装原則

- 既存 Stage 3.4 の挙動を可能な限り保持し、Stage 3.4b の新機能は config で有効化できる形を優先する。
- convergence 判定を緩くして既存結果を通す変更は禁止する。
- evidence が不足している場合は `converged` にしない fail-closed 方針とする。
- hard ceiling 到達時に未解決イベントがあれば、`converged` ではなく明示的な未収束状態にする。
- checkpoint / design-space version / seed の provenance を失わない。
- integer variable の比較は decoded design 値で行う。
- unique decoded designs と raw objective calls を混同しない。
- benchmark 結果を optimizer quality の比較に使用しない。

## 14.3 Step 1 — Stage 3.4b config の追加

Stage 3.4 の config を直接上書きせず、Stage 3.4b 用の新規 config を追加する。

推奨名:

```text
configs/next_50ohm_center_outer_same_stage34b.yaml
```

実際の repository で config 配置場所が異なる場合は既存慣例に従う。

必須変更:

```yaml
seeds:
  - 20260909
  - 20260910
  - 20260911
  - 20260912
  - 20260913
  - 20260914
  - 20260915
  - 20260916

optimizer_validation:
  parallel:
    seed_level: true
    production_workers: 8
    blas_threads_per_worker: 1

  budgets:
    - 16000
    - 32000
    - 48000
    - 64000
    - 96000
    - 128000
    - 192000
    - 256000
    - 384000

  optional_max_budget: 512000
  auto_escalate: true
  minimum_convergence_budget: 32000
```

`io_idt_pairs` は Stage 3.4b 開始時点から decoded lower bound 8 を探索可能にする。既存 schema に `initial` / `hard` / `lower_steps` がない場合は、同じ意味になる既存フィールドで表現すること。

**禁止:** `io_idt_pairs=8` を単一 coordinate probe のみで評価して探索空間から除外すること。

## 14.4 Step 2 — convergence evidence の拡張

convergence policy が受け取る evidence に、最低限以下を追加する。

```text
materially_improving_seed_fraction
final_primary_iqr
final_primary_median
final_primary_worst
final_primary_worst_minus_median
grid_converged_seed_count
grid_converged_seed_fraction
validation_gap_primary_median
validation_gap_primary_max
recovery_fired_at_current_checkpoint
recovery_pending_confirmation
boundary_pressure_first_seen_at_current_checkpoint
boundary_pending_confirmation
hard_bound_reached_by_variable
```

名前は既存 naming convention に合わせてよいが、review bundle から意味が一意に読めること。

各 evidence について、seed 数、対象 budget interval、design-space version を追跡可能にする。

## 14.5 Step 3 — material-improvement seed fraction gate

既に `fraction_seeds_improving_by_threshold` 相当が計算されている場合、そのロジックを重複実装せず再利用する。

Stage 3.4b の infeasible case では、最後の 2 paired intervals の両方について次を要求する。

```text
median plateau condition == PASS
AND
materially_improving_seed_fraction <= 0.25
```

8 seed では 2/8 は PASS、3/8 は FAIL である。

threshold の inclusive/exclusive は **`<= 0.25` を PASS** とする。

paired interval に必要な seed が欠落している場合、gate は PASS にしない。理由を evidence に出力する。

## 14.6 Step 4 — worst-seed spread gate

IQR だけで単一悪化 seed が隠れることを防ぐ。

infeasible case では final checkpoint の validated primary metric を seed ごとに集計し、

```text
worst_minus_median = max(primary_by_seed) - median(primary_by_seed)
```

を計算する。primary が「小さいほど良い」現在の infeasible violation metric であることを前提とする。

Stage 3.4b 初期 threshold:

```text
final_seed_primary_iqr <= 0.10
final_seed_primary_worst_minus_median <= 0.10
```

将来 metric の向きが変わっても破綻しないよう、既存 objective direction abstraction があるならそれを使う。

## 14.7 Step 5 — frequency-grid convergence gate

各 seed の final checkpoint で `grid_converged` を取得し、

```text
grid_converged_seed_fraction >= 0.875
```

を要求する。8 seed なら 7/8 PASS、6/8 FAIL。

同時に validation gap は median だけでなく max も review evidence に保存する。

adaptive grid が current checkpoint で更新された直後で、更新後 grid で再評価されていない場合は `grid_converged=true` にしない。

## 14.8 Step 6 — stagnation recovery pending gate

現在の checkpoint で stagnation recovery が発火し、population refresh / diversification が行われた場合、その checkpoint で convergence を許可しない。

最低要件:

```text
if recovery_fired_at_current_checkpoint:
    convergence = false
    recovery_pending_confirmation = true
```

次 checkpoint で実際に新しい interval を探索した後にのみ pending を解除できる。

解除条件は「次 checkpoint に到達した」だけでなく、refresh 後に正の unique evaluation 数が存在することを確認する。

同一 design-space version で recovery が複数回発火する場合も状態を壊さない。

## 14.9 Step 7 — boundary persistence pending gate

boundary pressure が初めて成立した checkpoint を収束 checkpoint にしてはいけない。

最低要件:

```text
if boundary_pressure_is_new_at_current_checkpoint:
    convergence = false
    boundary_pending_confirmation = true
```

既存 `required_persistent_checkpoints=2` がある場合は、その仕組みと統合し二重状態管理を避ける。

hard bound に到達済みで、それ以上拡張不能な variable は、単に pending を永久保持するのではなく、

```text
hard_bound_reached
```

として evidence に明示する。その状態で convergence を許可するかどうかは、既存 hard-bound policy と本計画の「hard-bound-limited 状態が未解決でないこと」に従う。

Stage 3.4b の `io_idt_pairs` lower side は開始時から hard lower bound 8 なので、8 への pressure 自体を「未実施 expansion」として扱わない。

## 14.10 Step 8 — hard ceiling と停止理由

512k は absolute hard stop とする。512k 到達時に certificate が成立しなければ、自動的に 768k / 1M などへ拡張しない。

停止理由は最低限、機械可読な enum / string で以下を区別する。

```text
converged
likely_underoptimized
inconclusive_at_hard_ceiling
failed_validation
runtime_error
```

既存 status 名がある場合は互換性を優先するが、`hard ceiling 到達` と `通常の underoptimized` を review で判別可能にする。

512k で current-checkpoint recovery、new boundary pressure、unresolved grid update、late material improvement のいずれかがある場合は `converged` 禁止。

## 14.11 Step 9 — parallel benchmark と production worker 決定

本番前に local machine 上で 4 / 6 / 8 workers を比較する preflight benchmark を追加または拡張する。

条件:

- 同一 8 seeds
- 同一小 budget
- 500–1000 unique decoded designs/seed を目安
- BLAS threads = 1
- quality comparison はしない

記録:

```text
worker_count
wall_time_sec
total_unique_designs
unique_designs_per_sec
cpu_model
physical_cores
logical_cores
ram_total_gib
ram_available_start_gib
ram_available_end_gib
peak_worker_rss_mb   # 取得可能なら
```

採用規則:

1. 8 workers で RAM pressure / swap / severe throughput degradation がなければ 8 workers。
2. 8 workers が 6 workers より明確に遅い、またはメモリ余力が危険なら 6 workers。
3. benchmark 自体のノイズが大きい場合は 8 workers を default とし、review に不確実性を書く。

**16 workers は今回の benchmark 対象外。**

## 14.12 Step 10 — local runtime metadata

run 開始時に実際のローカル実行環境を取得し、review bundle 内に保存する。

推奨:

```text
environment/local_runtime.json
```

最低限:

```json
{
  "cpu_model": "...",
  "physical_cores": 8,
  "logical_cores": 16,
  "ram_total_gib": 0.0,
  "ram_available_start_gib": 0.0,
  "production_workers": 8,
  "blas_threads_per_worker": 1,
  "platform": "Windows",
  "platform_release": "...",
  "python_version": "...",
  "run_start": "...",
  "run_end": "...",
  "wall_time_sec": 0.0
}
```

取得失敗したフィールドは null とし、推測値を書かない。

## 14.13 Step 11 — review bundle の既知不具合修正

Stage 3.4 review で確認された以下を修正する。

### A. REVIEW_ME / summary title

Stage 名を hard-code せず、run metadata / experiment name から生成する。Stage 3.4b run なのに `Stage 3.1 review summary` 等が出ないこと。

### B. budget 表示

summary 内の実際の config key と report generator の参照 key を揃え、`Budgets ...: None` にならないこと。

表示値は「unique decoded design checkpoint」であることを明記する。

### C. validated rank の生成順序

`best_candidates.json` を final validation / validated ranking より前に確定しない。

必須順序:

```text
candidate collection
→ final validation
→ validated rank tuple calculation
→ best candidate summary serialization
```

Stage 3.4b の best candidate entries で、validated ranking が利用可能なのに空配列 `[]` のままにならないこと。

## 14.14 Step 12 — テスト追加

最低限以下を unit / integration test に追加する。既存 fixture を再利用し、巨大 optimization run を test suite に入れない。

### Convergence gate tests

1. **2/8 improving = PASS**
   - material improvement fraction = 0.25
   - 他 gate 全 PASS
   - fraction gate PASS

2. **3/8 improving = FAIL**
   - fraction = 0.375
   - convergence FAIL

3. **IQR PASS / worst spread FAIL**
   - central seeds は密集
   - 1 seed のみ悪い
   - IQR threshold 内、worst-minus-median > 0.10
   - convergence FAIL

4. **grid 6/8 = FAIL**

5. **grid 7/8 = PASS**
   - 他 gate 全 PASS

6. **current checkpoint recovery = FAIL**
   - recovery fired
   - 他 gate 全 PASSでも convergence FAIL

7. **next checkpoint after recovery = PASS candidate**
   - refresh 後に unique evaluations > 0
   - pending cleared
   - 他 gate 全 PASSなら convergence 可

8. **new boundary pressure = FAIL**

9. **persistent boundary confirmed = PASS candidate**
   - policy 上解決済み
   - 他 gate 全 PASS

10. **hard ceiling unresolved = non-converged**

11. **evidence missing = fail closed**
   - 新 gate に必要な evidence が欠落
   - exception で run 全体を壊すのではなく、少なくとも convergence を PASS にしない

### Reporting tests

12. Stage title が experiment metadata と一致。
13. budget list が `None` にならない。
14. validated rank が validation 後に best candidate output へ反映。
15. local runtime metadata JSON schema が保存される。

## 14.15 Step 13 — regression test

変更後に既存 test suite を全実行する。

前回 review の baseline は、参考値として pytest 115/115、unittest 89/89 pass だったが、**現在の repository で実際に得られた変更前 baseline を正とする**。

以下を満たさない場合、本番 run を開始しない。

```text
new tests: all pass
existing tests: no new regressions
config load/validation: pass
short smoke run: pass
review bundle generation: pass
```

## 14.16 Step 14 — smoke run

本番前に Stage 3.4b config の縮小版で smoke run を行う。

目的:

- 8 seed scheduling
- worker process startup
- BLAS=1
- new convergence evidence serialization
- pending recovery/boundary fields
- grid convergence fields
- review bundle generation
- local runtime metadata

を確認すること。

smoke run の optimizer quality は評価しない。

## 14.17 Step 15 — Phase A benchmark 実行

ローカル Ryzen 7 PRO 4750G 上で 4 / 6 / 8 workers を測定する。

benchmark の結果を以下のような表で保存する。

```text
workers | wall_s | unique_designs | designs/s | peak_RSS | note
4       | ...    | ...            | ...       | ...      | ...
6       | ...    | ...            | ...       | ...      | ...
8       | ...    | ...            | ...       | ...      | ...
```

採用 worker 数と理由を `benchmark_decision.json` または review summary に残す。

## 14.18 Step 16 — Stage 3.4b production run

Phase A で選ばれた worker 数を使用し、8 cold seeds で実行する。

checkpoint ごとに convergence 判定し、certificate 成立時は以後の budget を実行しない。

ただし以下の場合は current checkpoint で停止禁止:

- current recovery fired
- new/unconfirmed boundary pressure
- required post-recovery interval 未実行
- grid update 未確認
- minimum convergence budget 未満

checkpoint progression は config に記載した順序を守る。

## 14.19 Step 17 — 本番終了後の自動判定

最終 status とともに、各 gate を一覧化する。

例:

```json
{
  "status": "converged",
  "final_budget": 96000,
  "gates": {
    "paired_plateau_1": true,
    "paired_plateau_2": true,
    "material_improvement_fraction": true,
    "final_iqr": true,
    "worst_minus_median": true,
    "late_improvement": true,
    "validation_gap": true,
    "micro_polish": true,
    "grid_converged_fraction": true,
    "recovery_confirmed": true,
    "boundary_confirmed": true
  }
}
```

status が non-converged の場合も、どの gate が失敗したかを必ず残す。

## 14.20 Step 18 — review bundle 作成

review bundle には最低限以下を含める。

```text
REVIEW_ME.md
config/
source_snapshot_or_hash/
results/
checkpoints/
convergence/
benchmark/
environment/local_runtime.json
tests/
```

既存 bundle layout がある場合はそれを維持し、本節の情報を追加する。

`REVIEW_ME.md` の冒頭には次を簡潔に表示する。

- experiment name
- final status
- final budget
- seed count
- worker count
- best validated candidate
- median / IQR / worst-minus-median
- grid-converged fraction
- recovery / boundary pending の有無
- wall time
- tests summary

## 14.21 Step 19 — 実装完了時に Codex が報告する内容

実装終了時は、コード変更だけでなく以下をまとめて報告すること。

1. 変更ファイル一覧。
2. 各変更の目的。
3. convergence 判定式の最終仕様。
4. 新規 config の主要値。
5. 新規/変更テスト一覧と結果。
6. baseline からの regression の有無。
7. smoke run 結果。
8. benchmark 結果と採用 worker 数。
9. production run を開始したか否か。
10. production run を開始していない場合、その理由。
11. 既知の未解決事項。

## 14.22 Codex に対する禁止事項

以下は明示的に禁止する。

- 収束しやすく見せるため threshold を緩和する。
- Stage 3.4 の既存結果ファイルを手で書き換える。
- COM/network numerical core を変更する。
- 仕様値、passband、stopband、50 Ω条件を変更する。
- seed を warm-start 化して cold-seed 統計と混在させる。
- unique designs と objective calls を同一 budget として扱う。
- 512k を超えて自動延長する。
- recovery 発火直後の checkpoint を converged とする。
- new boundary pressure 発生直後の checkpoint を converged とする。
- validation 前の ranking を final validated ranking として保存する。
- benchmark の objective 値を optimizer 品質比較に利用する。
- ローカル PC の CPU/RAM 情報を別環境から推測して書く。

## 14.23 Definition of Done

Stage 3.4b 実装は、以下をすべて満たしたときのみ完了とする。

- Stage 3.4b 専用 config が追加されている。
- `io_idt_pairs=8` が通常探索空間に含まれている。
- 8 cold seeds が設定されている。
- 4/6/8 worker benchmark が実行可能。
- material-improvement fraction gate が実装されている。
- worst-minus-median gate が実装されている。
- grid-converged fraction gate が実装されている。
- recovery pending gate が実装されている。
- boundary pending gate が実装されている。
- 512k hard ceiling が実装されている。
- review bundle の Stage title / budget / validated rank 問題が修正されている。
- local runtime metadata が保存される。
- 新規テストが全 PASS。
- 既存テストに regression がない。
- smoke run が完走する。
- benchmark 結果から production worker 数が決定されている。
- production run が再現可能なコマンドまたは entry point で開始できる。

---

# 15. Codex へ渡す短縮プロンプト

以下を Codex にそのまま渡してよい。

> `stage3_4b_experiment_plan.md` を実装仕様として読み、Stage 3.4b を実装してください。まずコードを変更せず現状の continuation / convergence / reporting / parallel execution の構造と既存テスト baseline を確認し、変更計画を短く提示してください。その後、Section 14 の手順に従って最小差分で実装してください。COM/network numerical core、目的関数、50 Ω仕様は変更禁止です。新しい convergence gate は fail-closed とし、recovery や boundary pressure が current checkpoint で発生した場合は収束を認めないでください。Stage 3.4b config は 8 cold seeds、`io_idt_pairs` lower bound 8、最大 512k hard ceiling、local benchmark 4/6/8 workers を使用します。実装後は新規テストと既存 regression test、smoke run を実行し、benchmark で production worker 数を決定してください。production run を開始する前に、変更内容・テスト結果・benchmark 結果を報告してください。

