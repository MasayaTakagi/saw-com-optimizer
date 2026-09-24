# Stage 3.8.6 Checkpoint Retention / Storage Cleanup 作業指示書

## 1. 目的

Stage 3.8C Production closeout、および Stage 3.8.5 Architecture Cleanup 後の構成を前提として、最適化実験で大量に生成される checkpoint の保存方式を整理する。

現在の問題は、長時間の DE / L-SHADE 実験で途中 checkpoint が多数残り、`runs/` の容量を大きく消費することである。

今回の目的は以下の4点とする。

1. **resume 用の重い checkpoint と解析用の軽量 history を分離する**
2. **実行中 checkpoint を `latest` / `previous` の原則2世代ローテーションにする**
3. **closeout 後に残す checkpoint を final / 明示的に pin されたものへ限定する**
4. **既存の Stage 3.8.5 の責務分離を崩さず、checkpoint lifecycle を共通 infrastructure として実装する**

今回の変更は storage / runtime infrastructure の改善であり、optimizer の性能改善ではない。

---

# 2. Stage 3.8.5 Architecture Cleanup から引き継ぐ前提

Stage 3.8.5 では少なくとも以下の整理が行われている前提で作業する。

- generic Review Bundle builder を canonical owner とする
- computation / reporting fingerprint を分離する
- counter / accounting 等の shared primitives を Stage 固有 runner から共通化する
- DMS topology を Stage 番号付き実装から切り離す
- historical Stage runner は互換性のため残してよい
- 新しい Stage では Stage 固有の ZIP / hash / accounting 実装をコピーしない

また、Stage 3.8 固有 report 生成には一部重複が残っている可能性があるが、これは今回の checkpoint cleanup の対象外とする。

**今回の作業を理由に Stage 3.8 report code の大規模整理を追加してはならない。**

---

# 3. 最重要原則

今回変更してよいのは、

```text
checkpoint persistence
checkpoint rotation
checkpoint retention
checkpoint finalization
history persistence
checkpoint artifact selection
```

である。

以下の numerical / optimization semantics は変更禁止。

```text
COM physics
network equations
material parameters
topology semantics
geometry constraints
manufacturing constraints
objective
filter specification
violation calculation
comparator ordering
canonicalization
integer rounding
initializer distribution
L-SHADE / DE algorithm
population update
selection logic
RNG draw order
seed semantics
evaluation budget
termination criterion
common validation grid
```

特に重要：

> checkpoint の「保存個数・保存場所・rotation」は変更してよいが、checkpoint が表現する optimizer state と resume 後の数値挙動は変更してはならない。

---

# 4. Historical Data 保護

Stage 3.8以前、および既に close 済みの production run は historical/canonical artifact として扱う。

今回の script 変更で、

```text
既存 runs の checkpoint を自動削除しない
既存 checkpoint format を一括変換しない
historical metadata を上書きしない
Stage 3.8 96k Production を再実行しない
```

こと。

既存 run の容量整理を行う utility を追加する場合も、

```text
dry-run default
明示的な run path 指定
削除対象一覧表示
削除前後サイズ表示
```

を必須とし、今回の作業中に historical production data へ cleanup を実行しない。

---

# 5. 目標となる保存モデル

## 5.1 実行中

概念的には以下とする。

```text
run/
├─ checkpoints/
│   ├─ latest.chk
│   └─ previous.chk
│
├─ history/
│   ├─ convergence.csv
│   ├─ best_history.csv
│   └─ population_stats.csv
│
├─ results/
│   ├─ best_design.json
│   └─ ...
│
└─ metadata/
    └─ ...
```

ファイル名・拡張子は既存 repository convention に合わせてよい。

重要なのは、

```text
重い resumable optimizer state
        ↓
原則2世代

軽い analysis history
        ↓
全期間保存
```

という責務分離である。

---

# 6. Resume Checkpoint Policy

通常実行時の full-state checkpoint は原則として、

```text
latest
previous
```

の2世代だけ保持する。

新 checkpoint 作成時は概念的に、

```text
1. 新stateをtemporary fileへ書く
2. write完了を検証
3. current latestをpreviousへrotate
4. temporaryをlatestへatomic replace
5. 不要な旧世代を削除
```

とする。

Windows 環境を含め、可能な限り同一 filesystem 内で atomic replace を使用する。

既存 writer / serializer がある場合は format を新設せず、それを利用する。

---

# 7. Crash Safety

checkpoint 容量削減のために recovery reliability を下げてはならない。

最低限以下を保証する。

### 正常時

```text
latest = 最新の完全 checkpoint
previous = 1世代前の完全 checkpoint
```

### latest が不完全・破損

既存 validation mechanism がある場合、

```text
latest invalid
    ↓
previous を resume candidate とする
```

ことが可能であること。

### temporary write 中に停止

temporary / partial file によって、

```text
latest
previous
```

の両方が同時に失われないこと。

既存 checkpoint に checksum / version / completeness validation がある場合は再利用する。

ない場合でも、今回の目的だけのために大規模な新 serialization framework を作らない。
必要最小限の sidecar metadata や atomic rename で対応する。

---

# 8. Analysis History の分離

full checkpoint に依存せず、optimizer の挙動を後から解析できるようにする。

最低限、既に取得している情報のうち以下を軽量 artifact として保存する。

```text
evaluation count
generation / iteration
best objective / score
best violation
best feasible status
population summary statistics
evaluation counters
checkpoint / milestone accounting
```

既存の、

```text
convergence CSV
seed result CSV
checkpoint accounting table
counter summary
```

等がすでに同じ役割を持つ場合はそれを canonical とし、重複ファイルを増やさない。

重要：

> 「checkpoint を消す代わりに、巨大な population dump を毎世代保存する」という実装にしてはならない。

analysis history は軽量であること。

---

# 9. Best Design と Best Checkpoint を区別する

通常の最適化結果として必須なのは、

```text
best design parameters
best validated metrics
seed
evaluation count
provenance
```

であり、必ずしも full optimizer checkpoint ではない。

したがって default は、

```text
best_design.json / CSV 等
```

を保存し、

```text
best full-state checkpoint
```

は自動的には永久保存しない。

full-state の best checkpoint を残す必要があるケースは、

- 後続計算をその state から継続する
- 特定 milestone を解析上 pin する
- 実験計画で明示的に要求される

場合に限定する。

---

# 10. Run 完了時の Finalization Policy

正常終了した run では、runtime checkpoint を finalization する。

概念的な最終状態：

```text
checkpoints/
├─ final.chk
└─ pinned/
    └─ <explicit milestone only>
```

または既存命名規則に合わせた同等構成とする。

正常 closeout 後は通常、

```text
latest
previous
temporary
ordinary intermediate full checkpoints
```

を永続 artifact として残さない。

ただし final checkpoint を生成するために state をコピーして容量を一時的に倍増させ続ける実装は避ける。

可能であれば最新 valid checkpoint を final として rename / promote する。

---

# 11. 異常終了時の扱い

異常終了時は cleanup を積極的に行わず、

```text
latest
previous
```

を recovery 用として残す。

run が、

```text
COMPLETED / CLOSED
```

と確定する前に resume data を削除してはならない。

closeout / finalization と checkpoint cleanup の順序は明示的にする。

---

# 12. Checkpoint Retention Class

artifact を概念的に3クラスへ分ける。

## A. Durable

長期保存対象。

```text
final checkpoint
explicitly pinned checkpoint
best design
final seed results
convergence/history
config
Git/provenance metadata
final summary
```

## B. Runtime Recovery

実行中のみ必要。

```text
latest checkpoint
previous checkpoint
```

## C. Ephemeral

通常は残さない。

```text
temporary checkpoint
superseded checkpoint
partial file
staging file
```

この分類をコードまたは documentation に明記する。

---

# 13. Canonical Owner

Stage 3.8.5 の architecture cleanup 方針を守り、Stage runner ごとに retention logic を実装しない。

作業開始時に repository を検索し、

```text
checkpoint
resume
save_state
load_state
checkpoint accounting
checkpoint lattice
rotate
finalize
```

の既存 implementation を inventory する。

## 原則

### checkpoint serialization / filesystem lifecycle

既存 canonical module があれば拡張する。

ない場合は概念的には、

```text
src/sawopt/io/checkpoints.py
```

のような IO responsibility 側を第一候補とする。

### checkpoint schedule / evaluation accounting

既に Stage 3.8.5 で整理された、

```text
optimization/
accounting
counters
checkpoint lattice validator
```

側の canonical implementation を維持する。

### 禁止

```text
stage3_9_xxx.py にrotate処理を直接実装
stageごとに別checkpoint managerを作成
reporting moduleにcheckpoint削除責務を持たせる
```

こと。

---

# 14. Reporting / Review Bundle との責務分離

Stage 3.8.5 で導入された generic Review Bundle builder の責務を維持する。

Review Bundle builder は、

```text
artifactを収集する
required / optionalを検証する
hashする
manifestを作る
ZIP化する
```

ものとし、

```text
checkpointをrotateする
checkpointを削除する
runをfinalizeする
```

責務を持たせない。

逆に checkpoint manager は、

```text
REVIEW_ME生成
ZIP生成
bundle manifest生成
```

を行わない。

---

# 15. Review Bundle に含める Checkpoint

Review Bundle の default は compact を維持する。

原則、

```text
全 intermediate checkpoint
```

を bundle に含めない。

必要に応じて、

```text
final checkpoint metadata
final checkpoint checksum
checkpoint policy metadata
```

を含める。

full final checkpoint 本体は large artifact として optional 扱いにできる。

既存 `ReviewBundleSpec` 等の mechanism がある場合はそれを利用し、Stage 固有の ZIP logic を追加しない。

---

# 16. Provenance / Metadata

新 run では checkpoint policy を追跡できるようにする。

最低限、metadata に概念的に以下を記録する。

```text
checkpoint_policy
checkpoint_retention_count
checkpoint_rotation_enabled
final_checkpoint_present
pinned_checkpoint_count
history_artifacts
```

具体的 field name は既存 schema convention に合わせる。

必要であれば、

```text
checkpoint_policy_version
```

を追加してよい。

ただし今回のためだけに provenance schema 全体を再設計しない。

---

# 17. Fingerprint v2 との関係

Stage 3.8.5 で導入された fingerprint v2 を崩さない。

今回の変更では、

```text
optimizer state meaning
resume numerical semantics
RNG behavior
```

に関係する code と、

```text
retention
rotation
file cleanup
artifact selection
```

の code を可能な限り分離する。

特に、

> pure storage policy change だけで numerical computation dependency が不用意に変化しない構造

を目指す。

ただし fingerprint dependency set は安全側に確認し、resume semantics に影響する serializer / restore logic を computation dependency から誤って外さない。

今回、

```text
fingerprint schema v3
```

のような新 schema は導入しない。

必要な provenance は既存 fingerprint v2 + Git metadata + checkpoint policy metadata で扱う。

---

# 18. Config

checkpoint policy を config 化する場合は既存 config style を使用する。

概念例：

```yaml
checkpoint:
  mode: rolling
  keep_previous: true
  keep_final: true
  keep_best_state: false
  pinned_milestones: []
```

これは概念例であり、既存 schema と競合する場合はそのまま採用しない。

重要なのは、

```text
default = rolling 2-generation recovery
```

とすること。

historical config の意味を変更しない。

---

# 19. Legacy Compatibility

既存 checkpoint loader を壊さない。

最低限、

```text
legacy checkpointを読み込める
legacy run directoryをreviewできる
historical Stage 3.8 artifactを変更しない
```

こと。

新 retention policy は原則、

```text
新規 run
```

へ適用する。

既存 run に新 policy を適用する migration は今回必須ではない。

---

# 20. Cleanup Utility を追加する場合

既存 completed run の容量整理に将来使える utility を追加してもよい。

ただし以下を必須とする。

```text
dry-run が default
run directory を明示指定
historical / running 状態を確認
削除候補を列挙
保持理由を表示
削除前サイズ
削除予定サイズ
削除後推定サイズ
```

例：

```text
KEEP  final.chk
KEEP  pinned_128k.chk
KEEP  convergence.csv
DELETE checkpoint_016k.chk
DELETE checkpoint_032k.chk
...
```

`--apply` 等の明示指定なしで削除しない。

repository 全体を横断して自動 cleanup する機能は今回作らない。

---

# 21. Atomicity Test

最低限、fixture / temporary directory を使って以下を test する。

### Test A — 1回目

```text
save checkpoint
→ latest exists
→ previous absent or valid empty-state handling
```

### Test B — 2回目

```text
save checkpoint
→ latest = #2
→ previous = #1
```

### Test C — 3回目

```text
save checkpoint
→ latest = #3
→ previous = #2
→ #1 full checkpoint no longer retained
```

### Test D — interrupted temporary write

```text
partial temp exists
→ last valid latest / previous remain recoverable
```

### Test E — corrupted latest

validation mechanism が存在する場合、

```text
latest invalid
→ previous candidate recognized
```

を確認する。

---

# 22. Resume Numerical Parity Test

今回もっとも重要な acceptance test の一つ。

fixed seed / small deterministic problem を用いて、

```text
A: uninterrupted run
B: checkpoint save → process stop相当 → resume
```

を比較する。

比較対象：

```text
final best design
final objective / violation
evaluation count
population state
RNG continuation
termination point
relevant counters
```

既存 tolerance / deterministic contract に従って一致すること。

checkpoint retention を変えたことで RNG draw order が変化してはならない。

---

# 23. History Completeness Test

checkpoint を削減しても解析 history が失われないことを確認する。

例えば、

```text
checkpoint interval = N
evaluation budget = M
```

の small run で、

```text
expected history rows
actual history rows
evaluation count monotonicity
best-history monotonic / expected semantics
counter consistency
```

を確認する。

既存 checkpoint lattice validator / accounting validator がある場合は必ず再利用する。

---

# 24. Finalization Test

正常終了 fixture に対し、

```text
before finalize:
latest + previous + history

after finalize:
final + history
```

となることを確認する。

explicitly pinned milestone がある場合のみ追加 full-state checkpoint を残す。

temporary / superseded checkpoint が残らないこと。

---

# 25. Review Bundle Integration Test

既存 generic builder を使って、

```text
completed fixture run
        ↓
review bundle
```

を生成する。

確認：

```text
bundle生成のためにoptimizerを再実行しない
intermediate full checkpointsを自動収録しない
final checkpoint metadataを取得可能
historyを収録可能
hash / manifest validation PASS
```

full checkpoint 本体を optional にした場合、その policy が manifest / metadata から判別できること。

---

# 26. Disk Usage Validation

小さな synthetic / smoke run で旧方式相当と新方式を比較する。

報告するもの：

```text
checkpoint write count
retained full checkpoint count
checkpoint total size
history total size
final run directory size
```

固定の削減率を acceptance gate にする必要はない。

ただし通常の長時間実行で、

```text
retained full checkpoint count = O(number of checkpoints)
```

から、

```text
retained runtime checkpoint count = O(1)
```

へ変わっていることを確認する。

---

# 27. Repository 保護

禁止：

```text
git reset --hard
git clean -fd
unrelated user changes削除
無断stash
無断commit
無断push
repository history rewrite
```

pre-existing dirty state は保持する。

今回の変更だけを scoped diff として記録する。

---

# 28. Stage 3.8 再実行禁止

今回の validation のために以下を実行しない。

```text
Stage 3.8 96k Production
Stage 3.8 8k
Stage 3.8 Pilot
大量 Monte Carlo
長時間 optimizer benchmark
```

必要なのは、

```text
unit test
integration test
small deterministic resume test
small smoke
```

のみ。

既存 Stage 3.8 saved artifact を read-only fixture として利用することは可。

---

# 29. 今回やらないもの

scope 外：

```text
Stage 3.9 topology implementation
ladder追加
hybrid DMS + ladder simulation
impedance sweep
optimizer tuning
new optimizer導入
COM calibration
material model変更
Stage 3.8 report generatorの全面分解
fingerprint v3
config体系全面刷新
cloud artifact store導入
repository-wide historical checkpoint一括削除
```

---

# 30. 推奨実行順

```text
Phase 0
Repository inventory / baseline
        ↓
Phase A
Canonical checkpoint owner確認
        ↓
Phase B
Rolling latest/previous implementation
        ↓
Phase C
History / full-state responsibility separation
        ↓
Phase D
Run finalization / retention policy
        ↓
Phase E
Review Bundle / provenance integration
        ↓
Targeted tests
        ↓
Resume parity test
        ↓
Full regression
        ↓
Small deterministic smoke
        ↓
Disk usage validation
        ↓
Review bundle作成
        ↓
STOP
```

---

# 31. Phase 0 — Baseline

変更前に最低限以下を保存する。

```text
git rev-parse HEAD
git branch --show-current
git status --short
git diff --stat
```

repository standard full test suite を実行し baseline を記録する。

Stage 3.8.5 終了時の test 数を決め打ちせず、

```text
現在の repository baseline
```

を source of truth とする。

pre-existing failure は今回の failure と区別する。

---

# 32. Stop Gate

各 Phase 完了時に targeted tests を実行する。

failure が出た場合は次 Phase へ進まず修正する。

test を通すために、

```text
optimizer behavior
numerical tolerance
RNG sequence
historical expected result
```

を変更してはならない。

---

# 33. Acceptance Criteria

## Architecture

- checkpoint retention logic の canonical owner が1つ
- Stage runner に新しい重複 implementation がない
- reporting builder が checkpoint deletion を担当していない
- accounting / lattice logic は既存 shared primitive を再利用

## Runtime

- latest / previous rotation PASS
- interrupted write safety PASS
- finalization PASS
- completed run で通常 intermediate full checkpoint が残らない

## Numerical Integrity

- fixed-seed uninterrupted vs resume parity PASS
- RNG continuation PASS
- evaluation accounting PASS
- optimizer result semantics unchanged

## History

- convergence/history completeness PASS
- full checkpoint 削減後も必要な解析情報が残る
- population full dump を history 代替として乱造していない

## Compatibility

- legacy checkpoint load PASS
- historical Stage 3.8 artifacts unchanged
- historical metadata unchanged

## Reporting

- generic Review Bundle builder を利用
- intermediate checkpoint を default bundle に含めない
- final checkpoint / policy metadata を必要に応じて扱える
- bundle hash / manifest validation PASS

## Regression

- targeted tests PASS
- full suite PASS
- small deterministic smoke PASS

## Historical Integrity

- Stage 3.8 96k rerun = NO
- Stage 3.8 Production files modification = NO
- Stage 3.9 implementation = NOT STARTED

---

# 34. Documentation 更新

最低限以下を更新する。

```text
checkpoint lifecycle
resume policy
artifact retention policy
run finalization
review bundle checkpoint handling
new experiment implementation guidance
```

特に以下を明記する。

> Full optimizer checkpoints are runtime recovery artifacts by default, not permanent experiment history.

> Analysis history must be stored separately from resumable optimizer state.

> New studies must reuse the canonical checkpoint lifecycle implementation instead of adding Stage-specific checkpoint rotation code.

---

# 35. Review Bundle

今回の変更自体について review bundle を作成する。

推奨名：

```text
stage3_8_6_checkpoint_retention_cleanup_review.zip
```

最低限含めるもの：

```text
REVIEW_ME.md
checkpoint_architecture_before_after.md
checkpoint_policy.md
test_summary.md
resume_parity_validation.json
rotation_validation.json
finalization_validation.json
history_validation.json
disk_usage_validation.json
review_bundle_validation.json
```

加えて既存 generic builder に従い、

```text
Git HEAD
git status
scoped diff
source tree / relevant source snapshot
SHA-256 manifest
```

を含める。

巨大な synthetic checkpoint 本体を review bundle に重複収録する必要はない。

---

# 36. REVIEW_ME.md に記載する内容

冒頭：

```text
Stage 3.8.6 Checkpoint Retention Cleanup:
PASS_AWAITING_REVIEW / FAIL_STOP
```

続けて最低限：

```text
1. changed modules
2. canonical checkpoint owner
3. rolling latest/previous result
4. atomic write / crash safety result
5. resume numerical parity result
6. history separation result
7. finalization / retention result
8. legacy compatibility
9. Review Bundle integration
10. fingerprint v2 impact
11. targeted tests
12. full tests
13. smoke test
14. disk usage before/after
15. known deferred items
```

を記載する。

---

# 37. 作業終了時の報告形式

```text
Stage 3.8.6 Checkpoint Retention Cleanup:
PASS_AWAITING_REVIEW / FAIL_STOP

Canonical checkpoint owner:
<module>

Rolling latest/previous:
PASS / FAIL

Crash-safe write:
PASS / FAIL

Resume numerical parity:
PASS / FAIL

RNG continuation:
PASS / FAIL

History separation:
PASS / FAIL

Finalization policy:
PASS / FAIL

Legacy checkpoint compatibility:
PASS / FAIL

Review Bundle integration:
PASS / FAIL

Fingerprint v2 regression:
PASS / FAIL

Targeted tests:
PASS / FAIL

Full suite:
<result>

Small smoke:
PASS / FAIL

Retained full checkpoints during run:
<count>

Retained full checkpoints after finalize:
<count>

Disk usage:
<before / after / reduction>

Stage 3.8 96k rerun:
NO

Historical production modification:
NO

Stage 3.9:
NOT STARTED

Review bundle:
<path>
```

その後停止すること。

---

# 38. 最終判断基準

今回の成功は単に checkpoint ファイル数が減ることではない。

以下が同時に成立していることを成功条件とする。

```text
容量削減
+
resume reliability
+
numerical reproducibility
+
analysis history保持
+
Stage非依存の共通実装
+
Stage 3.8.5で作った責務分離の維持
```

理想状態は、

```text
実行中:
    latest + previous

解析:
    lightweight history

終了後:
    final + explicitly pinned checkpoint only

report:
    generic Review Bundle infrastructure
```

となり、今後 Stage 3.9 以降で checkpoint 管理コードをコピーせずに済む状態である。
