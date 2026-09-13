# Codex 作業指示書
## Stage 3.5 L-SHADE Parity Root-Cause Investigation

### Mission

Phase C final confirmation で検出された L-SHADE parity failure の原因を特定し、
現行コードが historical Stage 3.5 D64 と同じ deterministic trajectory を再現できる状態へ戻す。

その後、**parity が復旧した場合にのみ**未実施の 4k/8k crossover と micro-polish を再開する。

**Phase D は開始しない。**

詳細仕様:
`stage3_5_lshade_parity_root_cause_experiment_plan.md`

---

# 1. 最重要ルール

parity が復旧するまで性能実験を増やさない。

禁止:

- 64k production rerun
- 128k / 192k
- optimizer tuning
- search-space tuning
- extra seeds
- historical Stage 3.5 winner の current code への自動継承

current result が historical より良くても parity PASS としない。

---

# 2. 最初の audit

コード変更前に以下を確認し、短い audit を出す。

## historical D64

- run path
- seed set
- selected parity seed
- source/commit hash
- config hash
- Python/NumPy
- BLAS/thread environment
- L-SHADE config
- terminal horizon
- checkpoint metadata
- RNG metadata
- canonicalization/objective version

## current

同じ項目。

## diff

特に:

- `lshade.py`
- shared DE code
- duplicate/cache
- checkpoint
- telemetry
- convergence
- diagnostic stop
- RNG
- decode/canonicalization

の差分を列挙。

分類:

- pure instrumentation
- control-flow-adjacent
- algorithmic

---

# 3. Baseline tests

実施:

- optimizer tests
- L-SHADE tests
- RNG/determinism tests
- cache/duplicate tests
- checkpoint/resume tests
- telemetry tests
- convergence tests
- reporting/status tests

既存 failure を記録。

---

# 4. Historical source reconstruction

historical D64 の exact source が repo/git history にある場合、
その source を reference として取り出す。

historical artifact の source hash と照合。

見つからない場合は:

```text
HISTORICAL_SOURCE_NOT_RECONSTRUCTABLE
```

と明記するが、artifact metadata から可能な限り比較を続ける。

historical provenance が想定と違った場合、
まず provenance mismatch を root cause 候補にする。

---

# 5. Initial-state parity

同じ seed/config で historical/current の初期状態を比較。

記録:

```text
raw_population_hash
decoded_population_hash
objective_vector_hash
rank_order_hash
archive_hash
mf
mcr
rng_state_hash
population_size
```

initial で不一致なら、
16kまで走らず原因を初期化側へ絞る。

---

# 6. Trajectory hash tracing

initial が一致した場合だけ進む。

checkpoint:

```text
initial
250
500
1000
2000
4000
8000
16000
```

unique decoded evaluations を基本軸とし、
generation ID も保存。

各 checkpoint:

```text
population_hash
decoded_population_hash
objective_hash
best_candidate_hash
best_rank
archive_hash
mf_hash
mcr_hash
rng_state_hash
population_size
generation
objective_calls
unique_evals
cache_hits
duplicate_attempts
accepted_trials
```

historical/current の first mismatch checkpoint を特定。

---

# 7. Event-level trace

first mismatch の直前区間だけ詳細 trace。

追跡:

```text
parent
pbest
donor indices
archive index
F
CR
crossover mask
mutant
trial
repaired trial
decoded trial
duplicate decision
cache decision
objective
selection result
archive update
memory update
population reduction
RNG state
```

historical/current の **最初の不一致イベント** を出す。

全runでverbose traceを出さない。

---

# 8. Root-cause classification

次のいずれかへ分類:

```text
RC1 RNG_CONSUMPTION_REGRESSION
RC2 DUPLICATE_CACHE_CONTROL_FLOW
RC3 POPULATION_SCHEDULE
RC4 ALGORITHMIC_LSHADE_CHANGE
RC5 DECODE_CANONICALIZATION_DRIFT
RC6 HISTORICAL_PROVENANCE_MISMATCH
RC7 TRUE_NONDETERMINISM
RC8 OTHER
```

`results/root_cause.json` に:

- category
- first divergence
- offending code
- why it changes trajectory
- fix
- regression prevention

を記録。

---

# 9. Fix

修正ルール:

- telemetry/logging は observer にする
- RNG draw を instrumentation が増やさない
- cache/duplicate counters が retry/selection を変えない
- diagnostic stop が terminal horizon を変更しない
- checkpoint serialize が state を変更しない
- unordered iteration が RNG/selection order に影響するなら deterministic order にする

historical algorithmic behavior に戻す場合は、
historical provenance が正しいことを確認してから行う。

---

# 10. Golden deterministic regression

mandatory。

小規模固定problemで 500–1000 unique eval 程度。

固定:

- seed
- config
- terminal horizon
- single-thread where feasible

fixture:

```text
initial_population_hash
mid_population_hash
final_population_hash
archive_hash
mf
mcr
best_candidate
best_rank
rng_state_hash
unique_eval_count
objective_call_count
```

test:

1. telemetry on/off same trajectory
2. progress callback on/off same trajectory
3. checkpoint serialization on/off same trajectory
4. diagnostic stop beyond checkpoint does not change pre-stop trajectory
5. cache metrics on/off same trajectory

golden fixture を自動更新しない。

---

# 11. Historical parity recheck

修正後に:

```text
S1
L-SHADE
same historical seed
terminal_horizon = 64000
diagnostic_stop = 16000
checkpoints = [4000,8000,16000]
```

で再実行。

initial / 4k / 8k / 16k を比較。

PASS:

```text
PARITY_RESTORED
```

FAIL:

```text
PARITY_STILL_FAILED_NEEDS_REVIEW
```

FAILならここで停止。

---

# 12. parity PASS 後のみ: 4k/8k crossover

S1 fixed。

## Legacy-DE

```text
same 4 seeds
cold start
diagnostic_stop = 8000
checkpoints = [4000,8000]
```

## L-SHADE

```text
same 4 seeds
cold start
terminal_horizon = 64000
diagnostic_stop = 8000
checkpoints = [4000,8000]
```

common validation を実施。

既存 16k / 32k / 64k と接続。

出力:

```text
optimizer_crossover_4k_64k.csv
optimizer_crossover_summary.json
optimizer_budget_curve_4k_64k.png
optimizer_paired_delta_4k_64k.png
```

---

# 13. parity PASS 後のみ: micro-polish

既存 final candidates:

- S0 + L-SHADE 64k × 4
- S1 + L-SHADE 64k × 4

既存 micro-polish policy をそのまま使用。

再optimizer runは禁止。

出力:

```text
micro_polish_results.csv
convergence_evidence_final.json
```

---

# 14. Final Stage 3.5 decision

parity PASS + crossover + micro-polish 完了後のみ再生成。

```json
{
  "optimizer_decision": "...",
  "search_space_decision": "...",
  "convergence_status": "...",
  "evidence_status": "...",
  "confirmed_crossover_interval": "..."
}
```

S0 rationale は:

> S1 に material gain がないため baseline S0 を維持

とする。

「S0は低次元だから」は禁止。

---

# 15. status/reporting bug

今回の failure path も修正する。

parity failure 時:

```text
status = PARITY_FAILED_REVIEW_WAITING
```

または既存 schema が限定的なら:

```text
status = REVIEW_WAITING
reason = PARITY_FAILED
```

`RUNNING` のままにしない。

未実施 crossover を `measured` と書かない。

データがない plot は通常plotとして出さない。

---

# 16. Tests

追加必須:

- deterministic initial population
- deterministic trajectory hash
- telemetry no-RNG-impact
- cache-counter no-control-flow-impact
- checkpoint observer purity
- diagnostic-stop / terminal-horizon separation
- parity failure status transition
- no false "measured" wording
- no-data plot handling
- golden fixture stability

既存 regression も実行。

---

# 17. 計算量制約

許可:

```text
root-cause debug: 1 seed, up to 16k
parity recheck: 1 seed × 16k
crossover after PASS:
  Legacy 4 × 8k
  L-SHADE 4 × 8k
micro-polish:
  existing 8 final candidates
```

禁止:

```text
64k production rerun
128k
192k
extra seeds
parameter sweep
```

追加計算が必要なら:

```text
NEEDS_REVIEW
```

で停止。

---

# 18. Review bundle

```text
runs/stage3_5_lshade_parity_root_cause/
├─ REVIEW_ME.md
├─ status.json
├─ results/
│  ├─ provenance_diff.json
│  ├─ provenance_diff.md
│  ├─ lshade_source_diff_audit.md
│  ├─ initial_state_parity.json
│  ├─ trajectory_parity.csv
│  ├─ first_divergence_event.json
│  ├─ first_divergence_trace.md
│  ├─ root_cause.json
│  ├─ fix_summary.md
│  ├─ golden_regression_result.json
│  └─ parity_recheck.json
├─ tests/
├─ config/
├─ environment/
└─ PARITY_ROOT_CAUSE_COMPLETE_WAITING_FOR_REVIEW.txt
```

parity PASS 後に final confirmation まで実施した場合のみ:

```text
optimizer_crossover_4k_64k.csv
optimizer_crossover_summary.json
micro_polish_results.csv
convergence_evidence_final.json
stage3_5_final_decision.json
```

---

# 19. REVIEW_ME.md 冒頭

```text
Root cause:
First divergence:
Fix:
Golden regression:
Historical parity:
Crossover executed:
Micro-polish executed:
Optimizer decision:
Search-space decision:
Convergence:
Tests:
Phase D started: NO
```

---

# 20. Stop rules

即停止:

1. historical provenance が特定不能で比較基準が壊れている
2. fix 後も parity failure
3. algorithmic change が意図的変更で、historical behaviorへ戻すべきか判断が必要
4. additional 64k run が必要になった
5. Phase D planning が必要になった

すべて review に回す。

---

# Definition of Done

- [ ] historical/current provenance 比較
- [ ] source diff audit
- [ ] initial parity
- [ ] first divergence 特定
- [ ] root cause 特定
- [ ] fix
- [ ] golden deterministic regression
- [ ] parity recheck
- [ ] failure path status/reporting 修正
- [ ] parity PASS の場合のみ crossover
- [ ] parity PASS の場合のみ micro-polish
- [ ] final decision 再生成
- [ ] tests green
- [ ] Phase D 未開始
- [ ] review waiting で停止
