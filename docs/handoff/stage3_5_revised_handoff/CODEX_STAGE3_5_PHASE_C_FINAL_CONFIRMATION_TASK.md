# Codex 作業指示書
## Stage 3.5 Phase C Final Confirmation

### Mission

Phase C 補完実験後に残った4点だけを解決する。

1. Legacy-DE → L-SHADE の short-budget crossover を 4k / 8k / 16k で直接確認
2. L-SHADE の `micro_polish_improvement` を埋め、convergence certificate を完成
3. S0 維持理由を「低次元」ではなく「S1 に material gain なし」へ修正
4. telemetry / convergence 修正後の L-SHADE が historical D64 と探索 parity を保つことを確認

**Phase D は絶対に開始しない。**

詳細仕様は
`stage3_5_phase_c_final_confirmation_experiment_plan.md`
を正本とする。

---

# 1. 最初に行うこと

以下を読む。

- `AGENTS.md`
- Stage 3.5 Phase C plan / config
- Phase C supplement plan / result
- latest review bundle
- Legacy-DE core
- L-SHADE core
- convergence certificate
- micro-polish implementation
- selector/reporting
- checkpoint/history code
- relevant tests

コード変更前に、短い audit report を出す。

最低限:

- historical B/D run paths
- B/D seed set
- historical D64 terminal horizon
- 4k / 8k / 16k checkpoint availability
- current L-SHADE source changes relative to historical D64
- existing micro-polish routine location
- existing materiality threshold source
- current selector wording
- tests to run

---

# 2. Baseline tests

変更前に relevant tests を実行。

最低限:

- optimizer
- L-SHADE
- Legacy-DE
- checkpoint/history
- convergence
- micro-polish
- selector
- reporting

可能なら full suite。

pre-existing failures を保存して区別する。

---

# 3. Step A — L-SHADE parity check

**crossover run より先に実施する。**

historical D64 の既存4 seedsのうち、
順序上最初の seed を使用する。

条件:

```text
search_space = S1
optimizer = L-SHADE
seed = first existing D64 seed
terminal_horizon = 64000
diagnostic_stop = 16000
checkpoints = [4000, 8000, 16000]
cold_start = true
```

historical D64 の同 seed / 16k checkpoint と比較。

比較:

- decoded best candidate
- common-validation metrics
- rank tuple
- population size
- unique decoded evaluations
- configuration
- RNG metadata
- checkpoint metadata

telemetry 値は instrumentation change で変わってよい。
探索結果が material に変わってはいけない。

既存 repository numerical tolerance を使う。
新規 tolerance を都合よく作らない。

### parity failure

material difference が出たら:

- crossover を開始しない
- 原因調査
- `PARITY_FAILED_NEEDS_REVIEW`
- review bundle生成
- STOP

---

# 4. Step B — paired 4k / 8k crossover diagnostic

parity PASS 時のみ。

## Legacy-DE

```text
search_space = S1
seeds = existing B/D same 4 seeds
cold_start = true
diagnostic_stop = 8000
checkpoints = [4000, 8000]
```

## L-SHADE

```text
search_space = S1
seeds = existing B/D same 4 seeds
cold_start = true
terminal_horizon = 64000
diagnostic_stop = 8000
checkpoints = [4000, 8000]
```

重要:

L-SHADE は `diagnostic_stop=8k` でも
population schedule は `terminal_horizon=64k` で計算する。

8k terminal L-SHADE として実行してはいけない。

---

# 5. Step C — common validation

4k / 8k checkpoint の best decoded candidate を
既存 Stage 3.5 common validation grid で再評価。

保存:

```text
seed
optimizer
terminal_horizon
checkpoint_budget
feasible
max_violation
sum_violation
worst_il_db
validated_rank
unique_decoded_evaluations
objective_calls
cache_hits
wall_time
```

budget 軸は unique decoded evaluations。

---

# 6. Step D — 4k→64k curve の構築

新規:

- 4k
- 8k

既存:

- 16k
- 32k
- 64k

を接続する。

S1 / same 4 seeds / Legacy-DE vs L-SHADE。

生成:

```text
results/optimizer_crossover_4k_64k.csv
results/optimizer_crossover_summary.json
plots/optimizer_budget_curve_4k_64k.png
plots/optimizer_paired_delta_4k_64k.png
```

budget ごとに:

- median
- P75
- worst
- IQR
- paired delta
- seed win count

を出す。

### crossover

以下を出す:

```text
first_observed_lshade_better_budget
confirmed_crossover_interval
crossover_reproduced
```

例:

```text
4k Legacy better
8k L-SHADE better

confirmed_crossover_interval = "(4k, 8k]"
```

4k ですでに L-SHADE が良ければ、

```text
crossover_reproduced = false
reason = "short-budget Legacy advantage did not reproduce under current Stage 3.5 conditions"
```

とする。

結果を過去結論へ無理に合わせない。

---

# 7. Step E — micro-polish

64k optimizer を再実行しない。

対象:

- S0 + L-SHADE 64k final candidate × 4
- S1 + L-SHADE 64k final candidate × 4

合計8。

既存 Stage 3.4b / current convergence policy の
micro-polish routine をそのまま使う。

変更禁止:

- algorithm
- neighborhood rule
- threshold
- polish budget
- acceptance criterion

ただし historical artifact から candidate 読み込みに adapter が必要なら追加可。

保存:

```text
seed
search_space
pre_rank
post_rank
micro_polish_improvement
micro_polish_material
polish_budget
stop_reason
accepted
```

routine が本当に利用不能なら null/unavailable。
`0.0` を偽装しない。

---

# 8. Step F — convergence certificate 再生成

C64 / D64 について:

- grid_converged
- recovery_pending_confirmation
- boundary_pending_confirmation
- hard_bound_unresolved
- micro_polish_improvement
- fraction_of_budget_at_last_significant_improvement
- search_space_exhausted
- stop_reason

を再評価。

**certificate を埋めることが目的であり、converged にすることが目的ではない。**

結果が未収束なら未収束と出す。

---

# 9. Step G — search-space decision wording 修正

禁止表現:

> S0 は低次元なので採用

S0/S1 は次元数差ではない。

human-readable decision:

```text
RETAIN_S0_NO_MATERIAL_S1_GAIN
```

rationale:

> S1 showed small aggregate improvements in median/P75 and won 3/4 seeds,
> but the gain did not exceed the existing materiality criterion and did not
> improve all robustness metrics; therefore retain baseline S0.

repository enum compatibility が必要なら mapping を入れてよい。

materiality threshold は repository/source-of-truth を再利用。
今回勝手に作らない。

---

# 10. Step H — final Stage 3.5 decision

出力を分離する。

```json
{
  "optimizer_decision": "...",
  "search_space_decision": "...",
  "convergence_status": "...",
  "evidence_status": "...",
  "confirmed_crossover_interval": "..."
}
```

optimizer:

- PROMOTE_LSHADE
- PROMOTE_LEGACY_DE
- OPTIMIZER_UNRESOLVED

search space:

- RETAIN_S0_NO_MATERIAL_S1_GAIN
- PROMOTE_S1
- SEARCH_SPACE_UNRESOLVED

convergence:

- converged
- likely_underoptimized
- inconclusive

---

# 11. 計算量制約

原則上限:

```text
L-SHADE parity:
  1 × 16k

Legacy crossover:
  4 × 8k

L-SHADE crossover:
  4 × 8k

micro-polish:
  8 existing final candidates
```

禁止:

- 64k arm rerun
- 4 seeds × 16k の追加 paired rerun
- 128k
- 192k
- extra seeds
- optimizer tuning
- search-space tuning

必要になった場合:

```text
NEEDS_REVIEW
```

で停止する。

---

# 12. Regression tests

追加/更新テスト:

1. terminal horizon と diagnostic stop が分離される
2. 8k diagnostic L-SHADE が 64k population schedule を使う
3. parity comparator
4. crossover interval calculation
5. 4k/8k historical connection
6. micro-polish unavailable を 0 にしない
7. certificate regeneration
8. S0 rationale に dimensionality を使わない
9. materiality threshold source-of-truth reuse
10. Phase D autostart prevention
11. review-waiting status

既存 physics / optimization regression を壊さない。

---

# 13. Review bundle

作成:

```text
runs/stage3_5_phase_c_final_confirmation/
├─ REVIEW_ME.md
├─ status.json
├─ results/
│  ├─ parity_check.json
│  ├─ optimizer_crossover_4k_64k.csv
│  ├─ optimizer_crossover_summary.json
│  ├─ micro_polish_results.csv
│  ├─ convergence_evidence_final.json
│  ├─ search_space_decision_final.json
│  └─ stage3_5_final_decision.json
├─ plots/
│  ├─ optimizer_budget_curve_4k_64k.png
│  ├─ optimizer_paired_delta_4k_64k.png
│  └─ micro_polish_improvement.png
├─ tests/
├─ config/
├─ environment/
└─ PHASE_C_FINAL_CONFIRMATION_COMPLETE_WAITING_FOR_REVIEW.txt
```

`status.json`:

```text
REVIEW_WAITING
```

---

# 14. REVIEW_ME.md 冒頭

必ず一目で分かる形で:

```text
Parity:
Crossover:
Optimizer decision:
Search-space decision:
Convergence:
Evidence completeness:
New compute:
Tests:
Phase D started: NO
```

本文:

- 4k Legacy vs L-SHADE
- 8k Legacy vs L-SHADE
- 16k/32k/64k接続
- crossover interpretation
- micro-polish
- convergence certificate
- S0 retention rationale
- remaining uncertainty
- next-phase note

---

# 15. 次Phase用メモ

Phase D は今回開始しない。

report には以下だけ残す:

> L-SHADE の population schedule は terminal horizon 依存。
> Phase D で192kまで検討する場合は、
> 192k terminal horizon の run に 128k checkpoint を設ける構成を優先して検討する。
> 128k terminal run を後から192kへ同一trajectoryとして単純延長しない。

正式な Phase D 計画はレビュー後に作成する。

---

# Definition of Done

- [ ] L-SHADE parity PASS、または failure を安全に報告
- [ ] paired 4k / 8k diagnostic 完了
- [ ] 4k→64k curve 完成
- [ ] crossover interval 判定
- [ ] 8 candidates micro-polish 完了
- [ ] convergence certificate 再生成
- [ ] S0 decision wording 修正
- [ ] final decisions 分離
- [ ] regression tests green
- [ ] review bundle 完成
- [ ] `REVIEW_WAITING`
- [ ] Phase D 未開始
