# Stage 3.5 Phase C 最終確認・追加実験計画

**対象:** SAW COM Optimizer / 50 Ω / Stage 3.5  
**位置づけ:** Phase C 補完実験後の最終確認  
**重要:** この計画が完了しても **Phase D は自動開始しない**。レビューbundleを生成して停止する。

---

## 1. 現時点の結論

Phase C 補完実験により、以下はかなり強く支持された。

### Optimizer

同一 S1 search space での common-validation median:

| Budget | Legacy-DE | L-SHADE |
|---:|---:|---:|
| 16k | 0.691075 | **0.682673** |
| 32k | 0.678501 | **0.672855** |
| 64k | 0.678501 | **0.656083** |

64k では 4/4 seeds で L-SHADE が Legacy-DE を上回った。

したがって、現在の SAW optimization problem を数万 unique decoded evaluations まで走らせる条件では、

> **L-SHADE を Stage 3.5 optimizer として採用する方向が妥当**

である。

ただし、過去の短 budget 比較では 4k 付近で Legacy-DE が L-SHADE より良かった。
今回の補完では 4k / 8k の Legacy-DE 側同条件データが不足しており、

> **Legacy-DE 優位 → L-SHADE 優位への crossover point**

はまだ直接確認できていない。

---

## 2. Search space の現状

公平な 64k horizon L-SHADE 比較:

| 指標 | S0 | S1 |
|---|---:|---:|
| median | 0.657492 | **0.656083** |
| P75 | 0.659338 | **0.658287** |
| worst | **0.663790** | 0.664755 |
| IQR | 0.002458 | **0.002338** |
| target hit | 4/4 | 4/4 |

seed 単位では S1 が 3/4 seeds で良いが、aggregate difference は小さい。

ここで重要なのは、S0 と S1 は「次元数」が違うのではなく、
主に search range / initialization policy の違いであること。

したがって S0 維持の理由は、

> 「低次元だから」ではなく、  
> **S1 に既存 materiality threshold を超える明確な改善が確認できないため baseline S0 を維持する**

と表現する。

既存 repository / Stage 3.4b / Stage 3.5 policy に materiality threshold が定義されている場合はそれを正本とし、
新しい threshold を今回の結果に合わせて作らない。

---

## 3. 残っている未解決事項

今回の追加実験は次の4点だけを解決する。

1. **4k / 8k / 16k のどこで optimizer 優位が変化するか**
2. **L-SHADE の `micro_polish_improvement` を実値で埋める**
3. **S0 維持理由を selector / report 上で正しく表現する**
4. **telemetry 修正後の L-SHADE が historical run と探索挙動 parity を保っているか確認する**

これ以外の optimizer tuning、search-space tuning、COM physics 変更は行わない。

---

# 4. 実験原則

## 4.1 64k production run は再実行しない

原則として禁止:

- S0 + L-SHADE 64k × 4 の再実行
- S1 + L-SHADE 64k × 4 の再実行
- Legacy-DE 64k × 4 の再実行
- 128k / 192k への延長

既存 Phase C / Phase C supplement artifact を再利用する。

## 4.2 budget 軸

budget は一貫して:

> `unique_decoded_evaluations`

を使用する。

`objective_calls` を optimizer budget の代用にしない。

## 4.3 validation

optimizer 内部 score だけで比較せず、
保存 candidate を同一 common validation grid で評価する。

---

# 5. Phase C-F0 — artifact / implementation parity audit

新規 crossover diagnostic より先に、
telemetry / convergence 修正後の L-SHADE が historical D64 と同じ探索挙動を保つことを確認する。

## 5.1 parity run

historical D64 から 1 seed を選ぶ。
原則として既存4 seedsの先頭 seed を用い、恣意的に「一致しやすいseed」を選ばない。

条件:

- search space: S1
- optimizer: L-SHADE
- current code
- same seed
- terminal horizon: 64k
- diagnostic stop: 16k
- checkpoints: 4k / 8k / 16k
- same problem/config/objective/canonicalization

比較対象:

- historical D64 の同 seed の 16k checkpoint
- 可能なら historical intermediate population/checkpoint metadata

比較項目:

- decoded best candidate
- validated max_violation
- validated sum_violation
- validated worst IL
- best rank tuple
- population size at checkpoint
- unique decoded evaluations
- objective calls / cache behavior（telemetry差は可）
- RNG/config/source metadata

## 5.2 parity 判定

今回追加した telemetry / reporting / convergence 修正は、
optimizer 探索ロジックを変えてはいけない。

既存 numerical regression tolerance が repository にある場合はそれを使用する。

それがない場合:

- metric delta
- decoded candidate delta
- rank delta

を明示して報告し、勝手な tolerance を新設しない。

**material な探索結果差が出た場合は crossover 実験へ進まず STOP**し、
原因を調査して review bundle を作る。

---

# 6. Phase C-F1 — 4k / 8k crossover diagnostic

parity が確認できた場合のみ実行する。

## 6.1 目的

過去:

- short budget では Legacy-DE 優位

現在:

- 16k / 32k / 64k では L-SHADE 優位

この間の crossover を current Stage 3.5 条件で直接測る。

## 6.2 条件

search space は **S1 に固定**する。

optimizers:

- Legacy-DE
- L-SHADE

seeds:

- existing B/D と同じ4 seeds

L-SHADE:

- **terminal horizon = 64k**
- diagnostic execution limit = 8k
- checkpoints = 4k / 8k

重要:

> `terminal horizon` と `今回実際に評価する diagnostic stop budget` を分離する。

L-SHADE の population reduction schedule は 64k horizon として計算する。
8k terminal schedule にしてはいけない。

Legacy-DE:

- diagnostic execution limit = 8k
- checkpoints = 4k / 8k

共通:

- cold start
- same seeds
- same S1
- same objective
- same decode/canonicalization
- same common validation grid

新規計算量は原則:

> 2 optimizers × 4 seeds × 8k

まで。

---

# 7. Phase C-F1b — 16k接続確認

既存 B/D には 16k data があるため、原則再実行しない。

以下を1つの budget table に接続する:

- new 4k
- new 8k
- existing 16k
- existing 32k
- existing 64k

ただし F0 parity によって current code と historical D64 の接続可能性が確認済みであることを条件とする。

Legacy-DE 側でコード変更が optimizer behavior に影響しうる場合は、
同様の parity check を1 seedだけ追加する。

---

# 8. crossover の定義

各 budget について同一4 seedsの common-validation aggregate を計算する。

最低限:

- median primary
- P75
- worst
- IQR
- seed-by-seed paired delta
- number of seeds won by each optimizer

primary は既存 feasibility-first policy に従う。

infeasible 同士なら既存 policy の `max_violation` を使う。

### `first_observed_lshade_better_budget`

L-SHADE aggregate median が Legacy-DE を初めて上回る最小 checkpoint。

### `confirmed_crossover_interval`

直前 checkpoint では Legacy-DE が優位、
次 checkpoint では L-SHADE が優位なら、

例:

```text
confirmed_crossover_interval = (4k, 8k]
```

とする。

もし 4k ですでに L-SHADE が優位なら、

> 今回の current Stage 3.5 条件では short-budget Legacy 優位は再現しなかった

と結論する。

過去の4k結果と無理に整合させない。

もし4k/8kとも Legacy優位で16kがL-SHADE優位なら、

```text
confirmed_crossover_interval = (8k, 16k]
```

とする。

---

# 9. Phase C-F2 — micro-polish certificate completion

64k optimization 本体は再実行しない。

対象:

- S0 + L-SHADE 64k final candidates: 4
- S1 + L-SHADE 64k final candidates: 4

合計8 candidates。

## 9.1 実行方法

既存 repository に Stage 3.4b / convergence certificate 用 micro-polish routine がある場合、
**同じ routine / thresholds / budget / neighborhood policy をそのまま再利用**する。

今回だけの新しい micro-polish algorithm や threshold を作らない。

対象 final candidate を post-processing 入力として与え、

- pre-polish validated rank
- post-polish validated rank
- improvement
- accepted/rejected
- polishing budget
- termination reason

を保存する。

## 9.2 必須出力

各 candidate に:

- `micro_polish_attempted`
- `micro_polish_improvement`
- `micro_polish_material`
- `micro_polish_budget`
- `micro_polish_stop_reason`

を実値で保存する。

未実装を `0.0` にしない。

routine が利用不能なら `unavailable` とし、
evidence status を `INCOMPLETE` のままにする。

---

# 10. Phase C-F3 — convergence evidence 再生成

micro-polish 後に C64 / D64 の convergence certificate を再生成する。

最低限:

- `grid_converged`
- `recovery_pending_confirmation`
- `boundary_pending_confirmation`
- `hard_bound_unresolved`
- `micro_polish_improvement`
- `fraction_of_budget_at_last_significant_improvement`
- `search_space_exhausted`
- `stop_reason`

を一覧化。

重要:

> certificate を完成させることと、`converged=true` にすることは別。

実データが non-converged を示すなら、
正しく `likely_underoptimized` / `inconclusive` と判定する。

threshold を結果に合わせて緩めない。

---

# 11. Phase C-F4 — S0/S1 decision wording 修正

既存結果:

- S1 が 3/4 seeds で良い
- S1 median もわずかに良い
- S0 worst はわずかに良い
- aggregate difference は小さい
- target hit は両方 4/4

したがって selector/report は、
「S0が性能で勝った」と表現しない。

推奨 decision semantics:

```text
optimizer_decision = PROMOTE_LSHADE
search_space_decision = RETAIN_S0_NO_MATERIAL_S1_GAIN
```

repository の enum compatibility が必要なら、
内部/JSONでは既存 enum を維持してよいが、
human-readable rationale は上記意味にする。

例:

```json
{
  "optimizer_decision": "PROMOTE_LSHADE",
  "search_space_decision": "RETAIN_S0_NO_MATERIAL_S1_GAIN",
  "search_space_rationale": "S1 showed small aggregate gains but did not exceed the existing materiality criterion; retain baseline S0.",
  "evidence_status": "..."
}
```

S0 を「低次元だから採用」と書かない。

---

# 12. Phase C-F5 — Stage 3.5 final decision

以下を分離して出す。

## 12.1 optimizer

候補:

- `PROMOTE_LSHADE`
- `PROMOTE_LEGACY_DE`
- `OPTIMIZER_UNRESOLVED`

今回の short-budget diagnostic は、
64k winner を覆すためではなく budget-dependent behavior を説明するためのもの。

ただし current-code 4k/8k/16k の結果が既存結論と重大に矛盾する場合は unresolved として STOP する。

## 12.2 search space

候補:

- `RETAIN_S0_NO_MATERIAL_S1_GAIN`
- `PROMOTE_S1`
- `SEARCH_SPACE_UNRESOLVED`

既存 materiality policy を用いる。

## 12.3 convergence

候補:

- `converged`
- `likely_underoptimized`
- `inconclusive`

micro-polish を含む evidence から機械的に判定する。

---

# 13. Phase D への引き継ぎメモ

今回 Phase D は開始しない。

ただし次回計画用に必ず記録する:

L-SHADE は terminal horizon により population schedule が変わるため、

> 128k terminal run を後から 192k に単純延長して同一 trajectory とみなさない。

Phase D で最大192kまで見る可能性があるなら、
原則として:

```text
terminal horizon = 192k
checkpoint = 128k
final = 192k if continuation criteria are met
```

という設計を検討する。

これは次回レビュー後に正式決定する。

---

# 14. 計算量上限

原則許可:

1. L-SHADE parity: 1 seed × 16k
2. crossover diagnostic:
   - Legacy-DE: 4 seeds × 8k
   - L-SHADE: 4 seeds × 8k
3. micro-polish: 8 final candidates

原則禁止:

- 64k production arm 再実行
- 4-seed 16k paired rerun
- 128k / 192k
- seed追加
- parameter sweep

追加計算が必要になった場合は自動拡大せず、
`NEEDS_REVIEW` として停止する。

---

# 15. 必須成果物

推奨 directory:

```text
runs/stage3_5_phase_c_final_confirmation/
```

最低限:

```text
REVIEW_ME.md
status.json

results/
  parity_check.json
  optimizer_crossover_4k_64k.csv
  optimizer_crossover_summary.json
  micro_polish_results.csv
  convergence_evidence_final.json
  search_space_decision_final.json
  stage3_5_final_decision.json

plots/
  optimizer_budget_curve_4k_64k.png
  optimizer_paired_delta_4k_64k.png
  micro_polish_improvement.png

tests/
environment/
config/

PHASE_C_FINAL_CONFIRMATION_COMPLETE_WAITING_FOR_REVIEW.txt
```

---

# 16. REVIEW_ME.md 必須内容

冒頭に:

- parity status
- optimizer decision
- search-space decision
- convergence status
- evidence completeness
- confirmed crossover interval
- new compute wall time
- tests
- Phase D not started

本文:

1. historical finding
2. new 4k/8k paired result
3. 16k/32k/64kとの接続
4. crossover interpretation
5. micro-polish result
6. final convergence certificate
7. S0/S1 decision rationale
8. unresolved items
9. Phase D planning note

---

# 17. 完了条件

- [ ] L-SHADE current-code parity を確認
- [ ] parity failureなら安全に停止
- [ ] S1 / 4 seeds / Legacy vs L-SHADE / 4k・8k比較完了
- [ ] 4k→64k budget curve完成
- [ ] crossover intervalを判定、または判定不能理由を明記
- [ ] 8 final candidatesにmicro-polish実施
- [ ] micro-polish evidenceを実値化
- [ ] convergence certificate再生成
- [ ] S0判断理由を修正
- [ ] optimizer/search-space/convergence decisionを分離
- [ ] regression tests green
- [ ] review bundle生成
- [ ] Phase D未開始
- [ ] review-waiting statusで停止
