# Stage 3.5 修正版実験計画
## Search-Space Design & Optimizer Efficiency Study — Corrected Plan

**対象:** SAW filter 50 Ω / DMS / `center_outer_same`  
**基準:** Stage 3.4b = 8 cold seeds, 256k unique decoded evaluations/seed で convergence certificate 成立  
**目的:** 解品質・certificate を落とさず、探索空間設計とOptimizer選択によって収束コストを削減する。

---

## 1. 今回の途中結果から修正する点

Phase A の科学的方向性は維持する。ただし以下を修正してから Phase C をやり直す。

1. Stage 3.5 entry point で canonical convergence config normalization を必ず通す。
2. Stage 3.4b → 現在コードの cross-version numerical parity を Phase A の必須gateにする。
3. local sensitivity で hard bound 外の未評価点を「外側改善」と誤認しない。
4. S1 の elite evidence は最終256kだけでなく 128k / 192k / 256k の late checkpointsを使用する。
5. Phase D certificate は missing evidence を PASS 扱いしない。未計測は `inconclusive_missing_evidence`。
6. 修正後は Phase C の A/B/C/D を同一 source/config hash で全て再実行する。旧A-armは比較証拠に再利用しない。

---

## 2. Phase A-R — 修正版offline diagnostics

### 2.1 Stage 3.4b artifact確認

exact review bundleから以下を確認する。

- convergence = `converged`
- checkpoint = `256000`
- 8 cold seeds
- exact source hash / git commit
- `validation_frequencies_hz` が各final seed recordに保存されていること

### 2.2 Cross-version numerical parity gate

Stage 3.4bの各seedの256k final designを、現在のリファクタリング後コードで再評価する。

再評価条件:

- design = historical final design
- Rs = Rl = 50 Ω
- wiring = `center_outer_same`
- validation grid = historical recordに保存された `validation_frequencies_hz`
- `passes=0`
- optimizerは一切実行しない

比較:

- saved `validated_rank_tuple`
- current re-evaluated rank tuple

全8 seedが数値parityを満たすことを必須とする。

**FAILならPhase Cへ進まない。**

### 2.3 Late elite evidence

S1設計には可能な限り以下を用いる。

- 128k
- 192k
- 256k

seed × checkpoint の late recordsを用い、256k finalだけに過度に依存しない。

### 2.4 Local sensitivity修正

hard bound外のperturbationは評価していないため、

`outside_improvement_suggested = False`

とし、

`error = outside_hard_bounds_not_evaluated`

として記録する。

「外側へ動けば改善する」という根拠には使わない。

---

## 3. Phase B-R — S1再生成・freeze

既存方針を維持する。

- hard boundsは変更しない
- variable固定は禁止
- narrow initial box + boundary driven expansion
- `io_idt_pairs` initial lower = 8を維持

Phase A-Rを通過後、S1を再生成する。

途中結果のS1 `[center_idt_pairs: 5–24]` は有力だが、**修正後diagnosticsから再生成された結果を正式S1とする。**

S1生成後:

- YAMLをfreeze
- SHA-256を記録
- Phase C/D中は変更禁止

---

## 4. Phase C-R — 4-arm screening 再実行

### Arms

- A = S0 + Legacy SciPy DE
- B = S1 + Legacy SciPy DE
- C = S0 + L-SHADE
- D = S1 + L-SHADE

### Seeds

- 20260917
- 20260918
- 20260919
- 20260920

### Checkpoints

- 16k
- 32k
- 64k

### 重要

旧途中runのA-armは再利用しない。

修正後のA/B/C/Dすべてを:

- same source hash
- same normalized base config
- same frozen S1 hash

で新規cold-startする。

### Promotion rules

従来のStage 3.5ルールを維持する。

- validated quality non-inferiorityを最優先
- target reach rate
- median unique evaluations to target
- worst-seed behavior
- boundary/recovery stability
- wall timeはsecondary

L-SHADEは新しいという理由だけでpromotionしない。

---

## 5. Phase D-R — Confirmatory certification

Phase C-Rでpromotion candidateが1つだけ選ばれた場合のみ実施。

### Arms

- baseline = S0 + Legacy DE
- variant = Phase C-R winner

### Fresh seeds

- 20260921 ... 20260928

### Checkpoints

- 16k
- 32k
- 64k
- 96k
- 128k
- 192k
- 256k

### Certificate policy

Stage 3.4bと同等のevidenceを要求する。

少なくとも以下が存在すること:

- grid convergence
- recovery pending state
- boundary pending state
- hard-bound unresolved state
- micro-polish improvement
- fraction of budget at last significant improvement
- validation gap

1つでも未計測なら:

`inconclusive_missing_evidence`

とする。

未計測を `False` / `True` の都合のよいdefaultへ変換してはいけない。

---

## 6. Success criteria

### 必須

- cross-version parity 8/8 PASS
- regression PASS
- final quality non-inferior
- Stage 3.4b相当certificate成立
- unresolved boundary/recoveryなし

### Efficiency

- 最低: median unique evals to target 30%以上削減
- 推奨: 40%以上削減
- stretch: 50%削減 ≒ 256k → 128k以下

---

## 7. Decision tree

### S1 + Legacy wins
探索空間設計が主ボトルネック。Legacyを維持してimpedance screening設計へ。

### L-SHADE wins
Optimizer family変更が有効。Legacyはreferenceとして保持。

### S1 + L-SHADE wins
探索空間とoptimizerのinteractionが重要。

### No clear winner
現baselineを保持し、次段で mixed-discrete / variable grouping / hierarchical parameterization を検討。

### S1 degrades quality
S1不採用。negative resultとして保存。

---

## 8. 今回やらないこと

- 3.4bを512kへ延長
- impedance sweep開始
- COM physics変更
- spec緩和
- CMA-ES等の追加
- Phase C seedをPhase Dへ流用
- 旧A-armと新B/C/Dを混在させる

