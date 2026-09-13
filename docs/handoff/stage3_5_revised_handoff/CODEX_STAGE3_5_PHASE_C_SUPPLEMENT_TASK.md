# Codex 作業指示書 — Stage 3.5 Phase C 補完

## Mission

Stage 3.5 Phase C の結果を公平な条件で補完し、

1. Legacy-DE と L-SHADE の budget-dependent crossover を確認する
2. L-SHADE 64k horizon で S0 と S1 を公平に比較する
3. L-SHADE の convergence evidence / telemetry 欠損を修正する
4. Stage 3.5 の optimizer winner / search-space winner を分離して判定する

こと。

**Phase D は開始しない。**
作業完了後は review bundle を生成し、レビュー待ちで停止する。

詳細実験仕様は `stage3_5_phase_c_supplement_experiment_plan.md` を正本とする。

---

# 1. 最重要制約

以下を変更しないこと。

- COM/network numerical core
- COM sign / phase convention
- 50 Ω 条件
- passband / stopband 仕様
- objective の意味
- feasibility-first ordering
- design decoding / canonicalization の意味
- Stage 3.4b / Stage 3.5 既存結果
- 過去 run artifact

optimizer tuning experiment は行わない。

L-SHADE の F/CR memory、archive、mutation/crossover、population reduction の数式を
今回の都合で tuning しない。

---

# 2. 作業開始時に読むもの

最初に:

1. `AGENTS.md`
2. 現行 Stage 3.5 experiment config / plan
3. Phase C review bundle
4. optimizer core:
   - Legacy-DE
   - L-SHADE
5. convergence policy
6. Stage 3.5 selector
7. checkpoint/history/reporting code
8. current tests

を確認する。

まずコード変更せず、次を短く報告する。

- A/B/C/D の run path
- 各 arm の optimizer / search space / terminal budget
- seed set
- D が 64k terminal horizon で cold start された証拠
- 既存 checkpoint candidate を4k/8k/16k/32k/64kで復元可能か
- L-SHADE convergence fields の欠損箇所
- Legacy elapsed time / duplicate telemetry の欠損原因
- `status.json` が review marker と不整合になる原因

その後に実装へ進む。

---

# 3. baseline

変更前に relevant tests を実行し保存する。

最低限:

- optimizer tests
- L-SHADE tests
- convergence policy tests
- Stage 3.5 study/selector tests
- checkpoint/resume tests
- reporting tests

可能なら full suite も実行。

pre-existing failure と今回の regression を混同しない。

---

# 4. 実装 Step A — convergence evidence 共通化

L-SHADE result が以下を実値で出せるようにする。

- `grid_converged`
- `recovery_pending_confirmation`
- `boundary_pending_confirmation`
- `hard_bound_unresolved`
- `micro_polish_improvement`
- `fraction_of_budget_at_last_significant_improvement`

原則:

> optimizer が evidence を「発明」するのではなく、
> study/convergence layer が optimizer-independent に計算する。

Legacy path に既に存在する generic logic があるなら再利用する。

欠損値を `false` / `0` で埋めて gate を通さない。

unknown は unknown として扱い、certificate は `inconclusive` にできる設計にする。

---

# 5. 実装 Step B — terminal horizon metadata

L-SHADE の trial/checkpoint/manifest に:

- `terminal_budget`
- `current_budget`
- `initial_population`
- `current_population`
- schedule identifier/version

を保存。

test を追加し、

- terminal=32k
- terminal=64k

では 32k 時点の population trajectory が異なり得ることを明示する。

32k terminal checkpoint を 64k terminal run の exact continuation と表示してはいけない。

---

# 6. 実装 Step C — telemetry 修正

## timing

全 optimizer で:

- `optimizer_wall_time_s`
- `validation_wall_time_s`
- `total_trial_wall_time_s`

を保存。

Legacy の `0.0` 固定を修正する。

## counters

全 optimizer:

- `objective_calls`
- `unique_decoded_evaluations`
- `cache_hits`
- `cache_hit_rate`

を同じ定義で保存。

`duplicate_decoded_rate` は numerator/denominator が正確に追跡できる場合のみ出す。
追跡不能なら `null`。

既存の意味不明な `duplicate_rate=0.0` を比較根拠にしない。

## status

manual review gate 到達時:

- marker file
- `status.json`

の両方を review-waiting に揃える。

---

# 7. 実装 Step D — optimizer crossover report

既存 B/D run を主に使用する。

比較:

- B: S1 + Legacy-DE
- D: S1 + L-SHADE

same seeds paired comparison。

budget checkpoints:

- 4k
- 8k
- 16k
- 32k
- 64k

可能な限り checkpoint の decoded candidate を同一 common validation grid で再評価する。

生成:

```text
results/optimizer_crossover.csv
results/optimizer_crossover_summary.json
plots/optimizer_budget_curve.png
plots/optimizer_paired_delta.png
```

CSV 最低列:

```text
seed
optimizer
search_space
terminal_budget
checkpoint_budget
feasible
max_violation
sum_violation
worst_il_db
validated_rank
objective_calls
unique_decoded_evaluations
cache_hits
optimizer_wall_time_s
```

summary:

- budget別 median/IQR/worst
- paired delta
- first crossover budget
- crossover 後の順位維持有無
- missing checkpoint evidence

---

# 8. crossover data が不足した場合

いきなり全 arm を再実行しない。

順序:

1. checkpoint/history から復元
2. saved decoded candidate の validation
3. それでも不足なら最小 paired diagnostic rerun

fallback rerun は最大:

- S1
- 2 same cold seeds
- Legacy-DE + L-SHADE
- L-SHADE terminal horizon = 64k
- checkpoints = 4/8/16/32k

64k final は既存 result が有効なら再実行しない。

fallback を実行した場合、production 4-seed result と混同しない。

---

# 9. 実行 Step E — S0 + L-SHADE 64k horizon

今回必須の新規 production run。

設定:

```text
search_space = S0
optimizer = L-SHADE
terminal_budget = 64000 unique decoded evaluations
cold_start = true
seeds = same 4 seeds as existing D
checkpoints = [4000, 8000, 16000, 32000, 64000]
```

重要:

- 旧 C 32k checkpoint から resume 禁止
- 64k terminal population schedule で最初から開始
- 4k/8k/16k/32k は同一64k trajectory 上の checkpoint
- common validation policy は D と同じ
- current production worker/BLAS policy を尊重
- ローカル計算資源を勝手に増やさない

run name 推奨:

```text
stage3_5_phase_c_s0_lshade_64k_fair
```

---

# 10. 実装 Step F — search-space selector 修正

比較:

- C64: S0 + L-SHADE / 64k terminal
- D64: S1 + L-SHADE / 64k terminal

same seed paired comparison。

selector output を少なくとも:

```json
{
  "optimizer_decision": "...",
  "search_space_decision": "...",
  "evidence_status": "..."
}
```

に分離する。

許容値:

optimizer:
- `PROMOTE_LSHADE`
- `PROMOTE_LEGACY_DE`
- `OPTIMIZER_UNRESOLVED`

search space:
- `PROMOTE_S0`
- `PROMOTE_S1`
- `SEARCH_SPACE_UNRESOLVED`

evidence:
- `COMPLETE`
- `INCOMPLETE`

既存の `PROMOTE_S0_LSHADE` のような合成値を互換のため残す場合でも、
内部判断は分離し、report には分離結果を出す。

---

# 11. S0/S1 比較 report

生成:

```text
results/search_space_comparison.csv
results/search_space_decision.json
plots/search_space_seed_comparison.png
```

最低限:

- feasible fraction
- median primary
- P75 primary
- worst primary
- IQR
- target hit count
- seed別 paired delta
- rank tuple

best seed 単独で winner を決めない。

S0 と S1 が実質同等なら、
「低次元 S0 を優先する」という tie-break を使ってよいが、
必ず equivalence tolerance と evidence を明記する。

差が不明確なら `SEARCH_SPACE_UNRESOLVED` とする。

---

# 12. tests

最低限追加する。

1. L-SHADE convergence evidence が dummy/default でなく計算される
2. missing evidence は converged を作れない
3. terminal 32k/64k metadata が区別される
4. 32k terminal checkpoint を64k exact continuationとして扱わない
5. timing が両 optimizer で正値または正当な nullable 値になる
6. cache hit rate の定義テスト
7. duplicate unavailable を0に偽装しない
8. review gate で status.json が review waiting になる
9. selector が optimizer/search-space decision を分離する
10. evidence 不足時に search space を勝手に S0 にしない
11. same-seed paired aggregate が正しく計算される
12. existing physics/numerical regression tests remain green

---

# 13. 実行順序

厳守:

```text
baseline tests
  ↓
evidence/telemetry/status patch
  ↓
targeted tests
  ↓
existing B/D crossover reconstruction
  ↓
必要なら最小 fallback diagnostic only
  ↓
S0 + L-SHADE 64k × 4 seeds
  ↓
common validation
  ↓
C64 vs D64 paired comparison
  ↓
Stage 3.5 decision
  ↓
full/relevant regression tests
  ↓
review bundle
  ↓
STOP
```

---

# 14. 禁止事項

- Phase D を開始しない
- 128k/192k を開始しない
- seed 数を勝手に増やさない
- A/B/D を理由なく再実行しない
- 旧 C を 64k へそのまま resume しない
- L-SHADE parameter tuning をしない
- Legacy-DE tuning をしない
- convergence threshold を結果に合わせて緩めない
- physics/objective/specification を変更しない
- historical run artifact を書き換えない
- best seed だけで winner を決めない
- missing evidence を PASS とみなさない
- objective_calls と unique decoded evaluations を混同しない
- local machine resources を推測で変更しない

---

# 15. review bundle

推奨:

```text
runs/stage3_5_phase_c_supplement/
├─ REVIEW_ME.md
├─ status.json
├─ config/
├─ results/
│  ├─ phase_c_supplement_summary.json
│  ├─ optimizer_crossover.csv
│  ├─ optimizer_crossover_summary.json
│  ├─ search_space_comparison.csv
│  ├─ search_space_decision.json
│  ├─ convergence_evidence.json
│  └─ telemetry_comparison.csv
├─ plots/
│  ├─ optimizer_budget_curve.png
│  ├─ optimizer_paired_delta.png
│  └─ search_space_seed_comparison.png
├─ checkpoints/
├─ tests/
├─ environment/
│  └─ local_runtime.json
└─ PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt
```

`REVIEW_ME.md` の冒頭には:

- optimizer decision
- search-space decision
- convergence status
- evidence completeness
- new run wall time
- reused runs
- new runs
- test result

を置く。

---

# 16. 最終報告

Codex の最終メッセージには以下だけを簡潔にまとめる。

1. 変更ファイル
2. テスト結果
3. 新規 run
4. 再利用 run
5. optimizer crossover の有無 / crossover budget
6. S0 vs S1 結果
7. optimizer decision
8. search-space decision
9. convergence status
10. unresolved items
11. review bundle path
12. **Phase D を開始していないこと**

長時間 run 中は無意味な polling を繰り返さず、
Python 側の checkpoint/progress を使うこと。

---

# Definition of Done

以下をすべて満たした時のみ完了。

- evidence/telemetry/status 修正が test 済み
- B vs D budget curve が作成済み
- 必要な場合のみ fallback diagnostic 実施
- S0 + L-SHADE 64k terminal × 4 cold seeds 完了
- C64 vs D64 common-validation paired comparison 完了
- optimizer/search-space decision 分離済み
- convergence evidence 欠損なし、または欠損を明示して inconclusive
- regression green
- review bundle 完成
- Phase D 未開始
- `PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt` 生成済み
