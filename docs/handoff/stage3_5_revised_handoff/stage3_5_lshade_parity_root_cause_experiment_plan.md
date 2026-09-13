# Stage 3.5 L-SHADE Parity Root-Cause 調査・再確認計画

**対象:** SAW COM Optimizer / 50 Ω / Stage 3.5  
**位置づけ:** Phase C final confirmation 中に検出された L-SHADE trajectory parity failure の原因調査  
**最優先事項:** 性能実験を増やす前に、現行 L-SHADE が historical D64 と同じ探索ロジックを再現できる状態か確認する  
**重要:** 本計画完了時点でも **Phase D は開始しない**

---

## 1. 背景

Phase C final confirmation で、以下の parity check を実行した。

- search space: S1
- optimizer: L-SHADE
- seed: historical D64 の先頭 seed
- terminal horizon: 64k
- diagnostic stop: 16k
- same problem / objective / decode / canonicalization を意図

しかし historical D64 と current code で、16k checkpoint の探索結果が一致しなかった。

例:

| 項目 | Historical D64 | Current code |
|---|---:|---:|
| max violation | 0.688218 | 0.678130 |
| sum violation | 3.630749 | 3.490631 |
| IDT gap | 1.04763 | 0.03204 |
| reflector gap | 0.10543 | 0.16847 |
| aperture | 116.79 | 124.00 |
| objective calls | 16638 | 16841 |
| cache hits | 764 | 837 |

同一 seed / same nominal config でも decoded best candidate と validated rank が一致していない。

したがって現在は、

> historical Stage 3.5 で得た L-SHADE の優位性を、現行コードへそのまま継承してよいか不明

という状態。

---

# 2. 今回の目的

今回の作業は性能最適化ではない。

次の5点を解決する。

1. historical D64 と current code の **最初の trajectory divergence point** を特定
2. divergence の原因コードを特定
3. telemetry / reporting / checkpoint / convergence 修正のうち、探索ロジックへ影響した変更があれば修正
4. fixed seed で deterministic trajectory regression test を追加
5. parity 復旧後にのみ、未完だった 4k/8k crossover と micro-polish を再開

---

# 3. 基本原則

## 3.1 まず原因調査。性能比較は禁止

parity が復旧するまで禁止:

- 64k production rerun
- optimizer winner 再判定
- S0/S1 winner 再判定
- 128k / 192k
- seed 追加
- optimizer tuning

## 3.2 「current が historical より良い」は parity PASS ではない

今回 current 16k の objective が historical より良かったとしても、
同じ seed / config で探索軌跡が変わった原因が不明な状態では PASS としない。

## 3.3 exact equality と material parity を分ける

調査フェーズではまず deterministic exact parity を目標とする。

ただし BLAS / floating-point 非決定性が本当に存在する場合のみ、
repository 既存 tolerance を使う。

今回の都合で新しい緩い tolerance を設定しない。

---

# 4. Phase P0 — Historical provenance 固定

最初に historical D64 の provenance を固定する。

最低限記録:

- run path
- seed
- source hash / commit hash
- config hash
- Python version
- NumPy version
- BLAS / thread config
- OS
- optimizer config
- search-space config
- terminal horizon
- initial population size
- population schedule
- RNG type
- RNG seed
- canonicalization version
- objective version
- validation grid version
- checkpoint schema version

current run についても同じ一覧を作り、差分表を生成する。

成果物:

```text
results/provenance_diff.json
results/provenance_diff.md
```

---

# 5. Phase P1 — Source diff 監査

historical D64 生成時点の code と current code を比較する。

最優先ファイル:

- `src/sawopt/optimizers/lshade.py`
- optimizer shared base / DE operators
- archive handling
- population reduction
- F / CR memory update
- mutation
- crossover
- boundary repair
- duplicate handling
- decode / canonicalization
- cache layer
- checkpoint / resume
- progress / telemetry hooks
- convergence hooks
- diagnostic-stop handling
- random-number handling

差分を分類する。

### A. Pure instrumentation
探索結果へ影響してはいけない変更

例:
- logging
- counters
- timing
- report fields
- JSON serialization

### B. Control-flow-adjacent
探索へ影響する可能性あり

例:
- duplicate retry
- cache hit handling
- callback
- checkpoint frequency
- diagnostic stop
- validation hook

### C. Algorithmic
明確に探索軌跡を変える変更

例:
- RNG call追加
- mutation/crossover変更
- population update変更
- archive update変更
- repair変更
- parameter memory更新変更
- population schedule変更

各差分に category と risk を付ける。

成果物:

```text
results/lshade_source_diff_audit.md
```

---

# 6. Phase P2 — Initial-state parity

16k から比較しない。
まず最初の状態を比較する。

同一 seed / same current-historical config で:

- initial decoded population
- initial encoded/raw population
- initial objective values
- initial rank order
- initial archive
- M_F
- M_CR
- RNG state
- population size

を比較。

推奨 hash:

```text
population_hash
decoded_population_hash
objective_vector_hash
rank_order_hash
archive_hash
mf_hash
mcr_hash
rng_state_hash
```

### 判定

#### initial state が不一致

原因候補:

- seed handling
- RNG type / initialization
- search-space initialization
- decode/canonicalization
- config mismatch
- source mismatch

ここで不一致なら generation-level investigation へ進まず、まず初期化原因を特定する。

#### initial state が一致

Phase P3へ進む。

---

# 7. Phase P3 — First-divergence tracing

initial state が一致する場合、
trajectory の最初の分岐を特定する。

## 7.1 Debug checkpoint

推奨 logical checkpoints:

- initial
- 250 unique eval
- 500
- 1k
- 2k
- 4k
- 8k
- 16k

ただし generation boundary と unique-eval boundary が一致しない場合は、
generation ID も記録する。

## 7.2 checkpoint state

各 checkpoint で:

- population hash
- decoded population hash
- objective vector hash
- best candidate hash
- best rank
- archive hash
- M_F hash/value
- M_CR hash/value
- RNG state hash
- population size
- generation counter
- objective calls
- unique decoded evals
- cache hits
- duplicate attempts
- accepted trial count
- successful F/CR sample count

を保存。

## 7.3 first divergence

最初に不一致になる state を特定する。

例:

```text
initial: match
250: match
500: match
1000: mismatch
```

なら 500→1000 のイベント列を詳しく追う。

---

# 8. Phase P4 — Event-level trace

first divergence 区間だけ detailed trace を有効化する。

全64kを詳細ログしない。

候補イベント:

- parent index
- p-best selection
- archive sample
- mutation donor indices
- F
- CR
- crossover mask
- repaired vector
- decoded vector
- duplicate decision
- cache hit/miss
- objective result
- selection accept/reject
- archive insertion/removal
- memory update
- population reduction event
- RNG state before/after critical draw

historical と current の **最初の不一致イベント** を特定する。

成果物:

```text
results/first_divergence_trace.md
results/first_divergence_event.json
```

---

# 9. Phase P5 — Root-cause classification

原因を以下のいずれかへ分類する。

### RC1: RNG consumption regression
telemetry / callback / retry 等で RNG draw 数が変化

### RC2: Duplicate/cache control-flow regression
cache hit / duplicate時の retry または selection経路変更

### RC3: Population schedule regression
terminal horizon / current budget の扱い変更

### RC4: Algorithmic L-SHADE regression
mutation / crossover / archive / memory update のロジック変更

### RC5: Search-space / decode / canonicalization drift
optimizer外の意味変更

### RC6: Historical provenance mismatch
historical artifact が想定 source/config と一致していない

### RC7: True nondeterminism
threading / BLAS / unordered iteration 等

### RC8: Other

根拠と修正方針を明記。

---

# 10. Phase P6 — 修正

修正原則:

- historical D64 を正しい reference behavior とみなすのは、
  historical provenance が正しいことを確認した場合のみ
- instrumentation は optimizer behavior から分離
- telemetry のために RNG を消費しない
- report/callback は pure observer にする
- duplicate/cache counters は control flow を変えない
- diagnostic stop は terminal horizon を変えない
- checkpoint serialization は state を変えない

修正後は targeted unit tests を追加。

---

# 11. Phase P7 — Golden deterministic regression test

今回の再発防止として mandatory。

固定条件:

- small deterministic test problem
- fixed seed
- fixed terminal horizon
- small budget（例 500–1000 unique eval）
- single-thread where possible

golden fixture 例:

- initial population hash
- checkpoint population hash
- archive hash
- M_F
- M_CR
- best candidate/rank
- final RNG state hash
- unique decoded eval count
- objective call count

test 要件:

1. pure telemetry変更で golden trajectory が変わらない
2. diagnostic stop を入れても stop 前 trajectory が変わらない
3. checkpoint serialization 有無で trajectory が変わらない
4. cache telemetry on/off で trajectory が変わらない

fixture 更新は明示的な algorithm version change 時のみ許可。

---

# 12. Phase P8 — Historical parity 再確認

修正後、同じ parity run を再実行。

条件:

- S1
- L-SHADE
- same historical D64 seed
- terminal horizon 64k
- diagnostic stop 16k
- checkpoints 4k / 8k / 16k

比較:

- initial state
- 4k
- 8k
- 16k

### PASS 条件

探索 state が deterministic reference と一致、
または repository 既存 tolerance 内。

PASS したら:

```text
PARITY_RESTORED
```

FAILなら:

```text
PARITY_STILL_FAILED_NEEDS_REVIEW
```

として停止。

---

# 13. Phase P9 — parity 復旧後のみ再開する実験

PARITY_RESTORED の場合だけ、
前回未実施だった final-confirmation を再開する。

## 13.1 4k/8k crossover

S1 fixed:

- Legacy-DE: 4 seeds × 8k
- L-SHADE: 4 seeds × 8k
- L-SHADE terminal horizon = 64k
- checkpoints = 4k / 8k

既存 16k / 32k / 64k と接続。

## 13.2 micro-polish

既存 final candidates:

- S0 + L-SHADE 64k × 4
- S1 + L-SHADE 64k × 4

計8 candidates。

既存 micro-polish policy を再利用。

## 13.3 decision regeneration

- optimizer decision
- search-space decision
- convergence status
- evidence status
- crossover interval

を再生成。

---

# 14. Status/reporting bug 修正

今回検出した reporting 不整合も修正する。

## 14.1 status.json

parity failure で停止した場合も:

```text
REVIEW_WAITING
```

または専用:

```text
PARITY_FAILED_REVIEW_WAITING
```

とし、`RUNNING` のままにしない。

## 14.2 REVIEW_ME

未実施の crossover を「measured」と書かない。

実データがない場合:

```text
4k/8k crossover: NOT RUN due to parity gate failure
```

とする。

## 14.3 plot

データがない場合、空グラフを通常結果として出さない。

代わりに:

- plot生成を省略
- または明示的 `NO DATA - PARITY GATE STOP`

とする。

---

# 15. 計算量制約

root-cause investigation は debug run を小さく保つ。

許可:

- parity debug: 1 seed
- checkpoints up to 16k
- detailed event trace は first-divergence 周辺のみ
- parity restore verification: 1 seed × 16k
- parity PASS 後の crossover: 2 optimizers × 4 seeds × 8k
- micro-polish: existing 8 candidates

禁止:

- parity不明のまま64k再実行
- 128k / 192k
- extra seeds
- parameter sweep

---

# 16. 必須成果物

推奨:

```text
runs/stage3_5_lshade_parity_root_cause/
```

最低限:

```text
REVIEW_ME.md
status.json

results/
  provenance_diff.json
  provenance_diff.md
  lshade_source_diff_audit.md
  initial_state_parity.json
  trajectory_parity.csv
  first_divergence_event.json
  first_divergence_trace.md
  root_cause.json
  fix_summary.md
  golden_regression_result.json
  parity_recheck.json

tests/
  golden_fixture/
  test_results.txt

config/
environment/

PARITY_ROOT_CAUSE_COMPLETE_WAITING_FOR_REVIEW.txt
```

parity が復旧し final confirmation まで実施した場合は追加:

```text
results/
  optimizer_crossover_4k_64k.csv
  optimizer_crossover_summary.json
  micro_polish_results.csv
  convergence_evidence_final.json
  stage3_5_final_decision.json
```

---

# 17. REVIEW_ME.md

冒頭:

```text
Root cause:
Fix status:
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

本文:

1. historical/current provenance
2. source diff
3. initial-state parity
4. first divergence point
5. first divergence event
6. root cause
7. code fix
8. golden deterministic regression
9. historical parity recheck
10. parity PASS 後の追加実験結果
11. unresolved items
12. Phase D not started

---

# 18. 完了条件

### parity root-cause phase

- [ ] provenance diff 完了
- [ ] source diff audit 完了
- [ ] initial-state parity 判定
- [ ] first divergence point 特定
- [ ] first divergence event 特定
- [ ] root cause 分類
- [ ] 必要な修正実施
- [ ] golden deterministic regression test 追加
- [ ] tests green
- [ ] historical parity recheck 完了

### parity PASS の場合のみ

- [ ] 4k/8k crossover 完了
- [ ] 4k→64k curve 完成
- [ ] micro-polish 完了
- [ ] convergence certificate 完成
- [ ] final Stage 3.5 decision 再生成

### 共通

- [ ] status が review waiting
- [ ] 未実施項目を report が誤記しない
- [ ] Phase D 未開始
