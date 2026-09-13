# Stage 3.5 Phase C 補完実験計画

**対象:** SAW COM Optimizer / 50 Ω / Stage 3.5  
**目的:** Phase C までの結果を公平な条件で補完し、Stage 3.5 の optimizer / search-space winner を確定する  
**重要:** 本計画完了後も **Phase D は自動開始しない**。レビュー用bundleを生成して停止する。

---

## 1. 背景

Phase C までの共通 validation grid 上の結果は以下。

| Arm | Search space | Optimizer | Budget | median max_violation | worst max_violation | Target到達 |
|---|---|---|---:|---:|---:|---:|
| A | S0 | Legacy-DE | 64k | 0.673110 | 0.680515 | 1/4 |
| B | S1 | Legacy-DE | 64k | 0.678501 | 0.707011 | 1/4 |
| C | S0 | L-SHADE | 32k | 0.666371 | 0.667533 | 2/4 |
| D | S1 | L-SHADE | 64k | 0.656083 | 0.664755 | 4/4 |

Stage 3.4b reference:
- `T_median = 0.666626`
- `T_best = 0.664755`

D は現時点で最も良い。ただし C と D は L-SHADE の terminal budget が異なる。

- C: L-SHADE population schedule の terminal budget = 32k
- D: L-SHADE population schedule の terminal budget = 64k

L-SHADE は terminal budget に応じて population reduction trajectory が変わるため、
C の 32k 結果を D の 64k trajectory の 32k checkpoint と同一視してはいけない。

また、過去の 4k 級比較では Legacy-DE が L-SHADE より良かった一方、
今回の 64k 級では L-SHADE が良い。
したがって「optimizer の優劣が budget により逆転するか」を直接確認する必要がある。

---

# 2. 今回の問い

この補完実験では次の4問だけに答える。

1. **Legacy-DE と L-SHADE の順位は budget に依存して逆転するか。**
2. **64k horizon の L-SHADE で S0 と S1 のどちらが良いか。**
3. **L-SHADE を Stage 3.5 winner として評価するための convergence evidence が揃っているか。**
4. **Phase D に進める winner を、同条件の evidence で1つに絞れるか。**

この4問に関係しない optimizer tuning、COM physics 変更、探索空間追加は行わない。

---

# 3. 実験設計の原則

## 3.1 計算時間を増やしすぎない

必須の新規 production optimization は原則として、

> **S0 + L-SHADE / 64k terminal horizon / 4 cold seeds**

だけとする。

既存の A/B/D 64k run は再利用する。

Legacy-DE vs L-SHADE の budget crossover は、まず既存履歴・checkpoint・best-so-far trace から再構成する。
既存データだけで判定できる場合、新規 optimizer run は追加しない。

## 3.2 比較は必ず同じ条件で行う

比較時に揃えるもの:

- 50 Ω
- 同じ SAW problem / physics
- 同じ objective / feasibility ordering
- 同じ seed set
- 同じ search space
- 同じ terminal horizon が必要な optimizer では同じ terminal horizon
- 同じ common validation grid
- 同じ candidate ranking
- unique decoded evaluations を budget 軸として使用

`objective_calls` を budget の代用にしない。

## 3.3 Phase D は自動開始禁止

本計画の最後は:

`PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW`

で停止する。

---

# 4. Phase C-S0 — 実装・データ監査

新規最適化を開始する前に以下を確認する。

## 4.1 既存 run の再利用可否

A/B/C/D について次を確認:

- seed
- optimizer
- search space
- terminal budget
- unique decoded evaluation count
- checkpoint budgets
- checkpoint candidate の保存有無
- best-so-far trace
- common validation grid
- source/config hash
- population schedule
- L-SHADE state / population history
- objective calls
- unique evaluations
- cache hits
- elapsed time

既存 D が 64k terminal horizon で最初から実行されていることを manifest で確認する。

## 4.2 checkpoint candidate の可用性

以下の budget で candidate を復元できるか確認:

- 4k
- 8k
- 16k
- 32k
- 64k

best-so-far scalar だけではなく、可能なら **decoded design** を復元する。

復元できる candidate は後述の common validation で再評価する。

---

# 5. Phase C-S1 — convergence / telemetry 修正

これは optimizer の探索挙動を変えるための改造ではなく、観測・判定を公平にするための修正。

## 5.1 L-SHADE convergence evidence

L-SHADE path でも以下を実値として出力する。

- `grid_converged`
- `recovery_pending_confirmation`
- `boundary_pending_confirmation`
- `hard_bound_unresolved`
- `micro_polish_improvement`
- `fraction_of_budget_at_last_significant_improvement`

未実装だから `false` を入れる、という対応は禁止。

generic study / convergence layer で計算できる evidence は optimizer 非依存に共有する。

## 5.2 terminal horizon を明示

L-SHADE result/manifest に最低限:

- `terminal_budget`
- `current_budget`
- `initial_population`
- `current_population`
- population reduction schedule version

を残す。

同じ seed、同じ 32k checkpoint でも terminal horizon が異なれば別 trajectory として扱う。

## 5.3 timing

全 optimizer で比較可能な wall time を保存する。

推奨:

- `optimizer_wall_time_s`
- `validation_wall_time_s`
- `total_trial_wall_time_s`

duration は可能なら `time.monotonic()` 系差分で計測する。

Legacy-DE の `elapsed_s = 0.0` のような欠損を比較値として使用しない。

## 5.4 duplicate/cache telemetry

定義が異なる `duplicate_rate` を無理に揃えない。

最低限、全 optimizer で:

- `objective_calls`
- `unique_decoded_evaluations`
- `cache_hits`
- `cache_hit_rate = cache_hits / objective_calls`

を出す。

decoded attempt 数を正確に追跡できる場合のみ:

- `duplicate_decoded_attempts`
- `duplicate_decoded_rate`

を追加する。

追跡できない場合は `null` / unavailable とし、`0.0` を偽装しない。

## 5.5 orchestration status

レビュー待ちになった時点で `status.json` もレビュー待ち状態へ更新する。

`RUNNING` のまま review marker だけ生成しない。

---

# 6. Phase C-S2 — optimizer crossover 解析

目的:

> 過去の短budgetでは Legacy-DE が良く、今回64kでは L-SHADE が良い理由が
> budget crossover で説明できるか確認する。

## 6.1 主比較

同一 search space の比較を優先する。

第一優先:

- B = S1 + Legacy-DE
- D = S1 + L-SHADE

同一 seed ごとに paired comparison を作る。

budget:

- 4k
- 8k
- 16k
- 32k
- 64k

横軸は `unique_decoded_evaluations`。

## 6.2 validation

各 checkpoint で保存された best decoded candidate を、
Stage 3.5 の同一 common validation grid で再評価する。

最低限記録:

- feasible
- max_violation
- sum_violation
- worst_il_db
- rank tuple

同一 seed 内で:

`delta_primary = L-SHADE - Legacy-DE`

を計算する。
infeasible primary が `max_violation` なら負値が L-SHADE 優位。

## 6.3 出力

最低限以下を生成:

1. seed別 best-so-far curve
2. optimizer別 median curve
3. optimizer別 IQR band
4. budget別 paired delta
5. first crossover budget

`first crossover budget` は、
L-SHADE の median validated primary が Legacy-DE を初めて上回る最小 checkpoint とする。

ただし単一点の逆転だけで結論づけない。
後続 checkpoint でも傾向が維持されるか併記する。

## 6.4 既存履歴が不足する場合

まず「不足している evidence」を report に記録する。

そのうえで、crossover 判定に不可欠な場合だけ fallback run を許可する。

fallback の優先順位:

1. 既存 checkpoint / history から decoded candidate 復元
2. 保存 candidate の再validationのみ
3. それでも不可能なら **同一2 seed の診断用 paired rerun**

診断用 rerun を行う場合:

- S1
- Legacy-DE vs L-SHADE
- same 2 cold seeds
- L-SHADE terminal horizon = 64k
- checkpoints = 4k/8k/16k/32k
- 64k final は既存 D/B を利用できるなら再実行しない

目的は crossover の位置確認であり、4-seed production result を置き換えない。

---

# 7. Phase C-S3 — S0 + L-SHADE 公平64k補完

これが今回の主たる新規 optimization。

## 7.1 条件

Arm C64:

- search space: S0
- optimizer: L-SHADE
- cold start
- terminal budget: **64k**
- seeds: 既存 D と同じ4 seeds
- validation: 既存 Stage 3.5 common validation policy
- checkpoints: 4k / 8k / 16k / 32k / 64k

重要:

> 旧 C の 32k terminal checkpoint から resume しない。

旧 C は 32k terminal schedule で population が縮小しているため、
64k horizon 比較には使用できない。

**64k terminal schedule で cold start から実行する。**

## 7.2 64k horizon の中間 checkpoint

4k/8k/16k/32k で run を終了させるのではなく、
64k terminal population schedule の同一 trajectory 上の checkpoint として保存する。

これにより:

- C64 の内部 convergence curve
- D64 との S0/S1 比較

を公平に行える。

---

# 8. Phase C-S4 — S0 vs S1 selection

比較:

- C64 = S0 + L-SHADE / 64k
- D64 = S1 + L-SHADE / 64k

同じ4 seedsを paired で比較する。

## 8.1 ranking

既存の feasibility-first policy を変更しない。

infeasible の場合の主順序:

1. max_violation
2. sum violations
3. worst IL

aggregate report では最低限:

- feasible fraction
- median primary
- 75th percentile primary
- worst primary
- IQR
- target hit count
- seed別 paired delta

を表示する。

## 8.2 search-space winner の判断

単に「best seed」が良い arm を選ばない。

以下を区別する。

### `PROMOTE_S0_LSHADE`

S0 が paired/aggregate の両方で同等以上で、
S1 の追加自由度に material benefit が認められない場合。

性能が実質同等の場合は、低次元である S0 を優先してよい。
ただし「同等」の根拠となる tolerance を report に明示する。

### `PROMOTE_S1_LSHADE`

S1 が median、paired seed consistency、worst-case の観点で
material に優れる場合。

### `SEARCH_SPACE_UNRESOLVED`

4 seeds で結果が混在し、
S0/S1 の差が不確定な場合。

この場合も Phase D を自動開始しない。
次のレビューで seed 追加の要否を判断する。

## 8.3 既存 selector の修正

現在の evidence なしに `PROMOTE_S0_LSHADE` を返すロジックがある場合は修正する。

selector は:

- optimizer winner
- search-space winner
- evidence completeness

を分離して出力する。

例:

```json
{
  "optimizer_decision": "PROMOTE_LSHADE",
  "search_space_decision": "PROMOTE_S1",
  "evidence_status": "COMPLETE"
}
```

または:

```json
{
  "optimizer_decision": "PROMOTE_LSHADE",
  "search_space_decision": "UNRESOLVED",
  "evidence_status": "COMPLETE"
}
```

---

# 9. Phase C-S5 — Stage 3.5 最終判定

以下を別々に判定する。

## 9.1 Optimizer decision

候補:

- `PROMOTE_LSHADE`
- `PROMOTE_LEGACY_DE`
- `OPTIMIZER_UNRESOLVED`

主 evidence:

- S1 64k paired comparison
- budget crossover curve
- target hit count
- seed robustness
- convergence diagnostics

4kだけの結果と64kだけの結果を混ぜて単一順位としない。
budget-dependent behavior として説明する。

## 9.2 Search-space decision

候補:

- `PROMOTE_S0`
- `PROMOTE_S1`
- `SEARCH_SPACE_UNRESOLVED`

必ず同じ optimizer、同じ64k terminal horizon で比較する。

## 9.3 Convergence status

候補:

- `converged`
- `likely_underoptimized`
- `inconclusive`

既存 convergence policy を尊重する。

missing evidence を `false` として PASS 扱いしない。

---

# 10. Phase D 進行 Gate

Phase D へ進めるための条件:

1. optimizer decision が unresolved でない
2. search-space decision が unresolved でない
3. required convergence evidence が欠損していない
4. common validation comparison が完了
5. status / timing / cache telemetry の整合性が取れている
6. regression tests が green
7. review bundle が完成

ただし上記を満たしても **Phase D を自動開始しない**。

レビュー待ちで停止する。

---

# 11. 計算量を抑えるルール

必須 production rerun:

- `S0 + L-SHADE / 64k / 4 seeds` のみ

禁止:

- A を再実行
- B を理由なく再実行
- D を理由なく再実行
- C 旧32kを64kへresume
- optimizer parameter sweep
- seed 数を自動増加
- 128k/192kへ自動延長

追加 rerun は「既存ログでは crossover が復元不能」の場合だけ。

---

# 12. 必須成果物

推奨 run:

```text
runs/stage3_5_phase_c_supplement/
```

最低限:

```text
REVIEW_ME.md
results/
  phase_c_supplement_summary.json
  optimizer_crossover.csv
  optimizer_crossover_summary.json
  search_space_comparison.csv
  search_space_decision.json
  convergence_evidence.json
  telemetry_comparison.csv
plots/
  optimizer_budget_curve.png
  optimizer_paired_delta.png
  search_space_seed_comparison.png
checkpoints/
config/
tests/
environment/
  local_runtime.json
PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt
```

`status.json` も review-waiting 状態にする。

---

# 13. REVIEW_ME.md に必ず書くこと

冒頭に:

- final Stage 3.5 status
- optimizer decision
- search-space decision
- evidence completeness
- new optimization wall time
- reused run IDs
- newly executed run IDs
- test summary

本文で:

1. 4k時点の Legacy-DE vs L-SHADE
2. 8k/16k/32k/64k の推移
3. crossover が存在するか
4. crossover budget
5. L-SHADE の長budget優位が何seedで再現したか
6. S0 vs S1 の64k公平比較
7. convergence gate一覧
8. 未解決事項
9. Phase D を開始していないこと

---

# 14. 解釈上の注意

今回確認したいのは「普遍的にL-SHADEが優れているか」ではない。

結論は次の粒度に限定する。

> 現在の 50 Ω SAW optimization problem、現在の search space、
> 現在の budget range において、どの optimizer/search space が
> Stage 3.5 後続実験に最も適しているか。

短budgetでLegacy-DEが強く、長budgetでL-SHADEが強いなら、
それ自体を正しい結果として report する。

---

# 15. 完了条件

以下をすべて満たしたら Phase C 補完完了。

- [ ] 既存 A/B/D を再利用できた
- [ ] L-SHADE convergence evidence が実値で出る
- [ ] timing/cache telemetry が定義付きで比較できる
- [ ] optimizer budget curve が作成された
- [ ] 4k/8k/16k/32k/64k の paired comparison が可能な範囲で完成
- [ ] S0 + L-SHADE 64k horizon × 4 seeds が完了
- [ ] C64 vs D64 を同条件で比較した
- [ ] optimizer decision を出した
- [ ] search-space decision を出した
- [ ] unresolved の場合は unresolved と明記した
- [ ] regression tests が通った
- [ ] review bundle を作成した
- [ ] Phase D を開始せずレビュー待ちで停止した
