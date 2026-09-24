# Stage 3.8.6 Checkpoint Retention Cleanup — Correction 作業指示書

## 1. 目的

Stage 3.8.6 Checkpoint Retention Cleanup のレビュー結果を受け、close前に必要な最小限の修正を行う。

今回のCorrectionで扱う問題は2点のみ。

1. 実行途中・REVIEW_WAITING時のartifactが、まだ存在しない `final` checkpoint pathを参照しうる
2. generic checkpoint lifecycle implementation がStage固有review marker名へ依存している

今回の修正では、checkpoint retentionの基本設計そのものは維持する。

```text
実行中:
    latest + previous

解析:
    lightweight history

正常終了後:
    final

review待ち / failure:
    latest + previous を保持
```

追加のoptimizer探索・長時間runは行わない。

---

# 2. 現状評価

Stage 3.8.6の主要機能はすでにPASSしている。

確認済み事項：

```text
CheckpointStore canonicalization        PASS
latest / previous rotation              PASS
atomic replace                          PASS
corrupt latest fallback                 PASS
L-SHADE resume numerical parity         PASS
RNG continuation                        PASS
lightweight history separation          PASS
normal finalization                     PASS
Review Bundle responsibility split      PASS
legacy checkpoint compatibility         PASS
full regression                         PASS
```

今回のCorrectionはこれらを作り直す作業ではない。

既存PASS behaviorを保存しながら、lifecycle contractだけを明確化する。

---

# 3. 最重要原則

今回変更してよいのは、

```text
checkpoint reference metadata
run lifecycle disposition
review-waiting / failed / completed finalization decision
legacy review marker compatibility
related tests / docs
```

のみ。

変更禁止：

```text
COM physics
network equations
material parameters
topology semantics
objective
filter specification
geometry constraints
L-SHADE algorithm
DE algorithm
selection
population update
RNG draw order
seed semantics
evaluation budget
termination semantics
checkpoint serialization payload
checkpoint restore numerical semantics
history semantics
```

resume numerical parityを必ず維持する。

---

# 4. 問題A — 存在しない final checkpoint reference

## 4.1 現状の問題

managed checkpoint modeでは、途中result metadata等が概念的に、

```text
checkpoint = .../checkpoints/final.json
```

を記録する場合がある。

しかしrun途中では実際に存在するのは、

```text
latest
previous
```

であり、

```text
final
```

は正常finalize後にしか存在しない。

したがって、

```text
途中artifact
REVIEW_WAITING artifact
aborted artifact
```

が存在しないphysical pathをcheckpointとして記録する可能性がある。

これはoptimizer numerical behaviorの問題ではないが、artifact provenanceとして不正確である。

---

# 5. Checkpoint Reference の新しい意味論

今後、run途中のartifactは、

```text
future final checkpoint path
```

を「現在のcheckpoint」として記録してはならない。

推奨は、physical checkpoint fileではなくlogical checkpoint streamを記録すること。

概念例：

```json
{
  "checkpoint_policy": "rolling_latest_previous",
  "checkpoint_stream": "trials/seed_001/checkpoints",
  "checkpoint_state": "runtime_recovery"
}
```

必要であれば、

```json
{
  "latest_checkpoint": ".../checkpoints/latest.json"
}
```

を記録してもよい。

ただしその場合は、

```text
artifact生成時点で実際に存在するpath
```

のみを記録すること。

---

# 6. final checkpoint の記録

`final` checkpointは、runの正常finalizationが成功した後にのみ、

```text
final_checkpoint
```

として記録する。

概念例：

```json
{
  "run_disposition": "COMPLETED",
  "final_checkpoint": ".../checkpoints/final.json"
}
```

REVIEW_WAITING / FAILEDでは、

```text
final_checkpoint
```

を存在するものとして記録しない。

必要なら、

```text
recovery_checkpoint_stream
```

等で表現する。

---

# 7. 既存APIの扱い

現在、

```text
LShadeCheckpointSession.reference_path
```

等が `final` pathを返している場合、その意味論を調査する。

今回のCorrectionでは、

```text
reference_path
```

を無条件にfinalへ向ける設計はやめる。

選択肢：

```text
A. current recoverable pathを返す
B. physical path APIとlogical stream APIを分離
C. legacy propertyをcompatibility用に残し、新APIをcanonicalにする
```

のいずれでもよい。

ただし、

```text
途中artifact → future final path
```

という状態を残さないこと。

大規模API redesignは不要。

---

# 8. 問題B — Generic Core の Stage 固有 marker 依存

## 8.1 現状の問題

generic checkpoint module内に概念的に、

```text
PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt
PHASE_C_FINAL_CONFIRMATION_COMPLETE_WAITING_FOR_REVIEW.txt
STAGE3_6_GATE2B_A_COMPLETE_WAITING_FOR_REVIEW.txt
...
```

のようなStage固有marker名が存在している。

これはStage 3.8.5で定めた、

```text
generic infrastructure
        ≠
Stage-specific semantics
```

という責務分離に反する。

Stage 3.9以降でreview markerが増えるたびに、

```text
src/sawopt/io/checkpoints.py
```

等のcore moduleを変更する構造にしてはならない。

---

# 9. Explicit Run Disposition の導入

checkpoint finalization decisionは明示的なrun lifecycle stateで行う。

最低限、次の3状態を表現する。

```text
COMPLETED
REVIEW_WAITING
FAILED
```

必要であれば既存命名規則に合わせてよい。

ただし意味論は明確にする。

---

# 10. Disposition Semantics

## COMPLETED

```text
optimizer/study execution completed
result artifacts written
close条件を満たす
```

場合。

checkpoint policy：

```text
latest valid state
    ↓
finalへpromote
previous削除
temporary削除
```

---

## REVIEW_WAITING

計算は完了しているが、人間レビュー・gate判断前である状態。

checkpoint policy：

```text
latest保持
previous保持
finalizeしない
```

review後に再開・再評価・追加処理があり得るため、recovery stateを残す。

---

## FAILED

例外・validation failure・aborted run等。

checkpoint policy：

```text
latest保持
previous保持
finalizeしない
```

failure cleanupのためにresume stateを消してはならない。

---

# 11. Success 判定の見直し

現在、

```python
status is None
    → success
```

のようなheuristicがある場合、checkpoint deletion/finalizationの最終判断には使用しない。

checkpoint deletionは不可逆操作なので、

```text
explicit lifecycle disposition
```

をsource of truthとする。

つまり、原則として、

```text
COMPLETED
```

が明示されない限りfinalizeしない方向を推奨する。

安全側は、

```text
unknown
    → preserve recovery checkpoint
```

とする。

---

# 12. API 概念例

厳密にこのAPIにする必要はない。

例：

```python
complete_study_run(
    run_dir=run_dir,
    result=result,
    disposition=RunDisposition.COMPLETED,
)
```

review待ち：

```python
complete_study_run(
    run_dir=run_dir,
    result=result,
    disposition=RunDisposition.REVIEW_WAITING,
)
```

failure：

```python
complete_study_run(
    run_dir=run_dir,
    result=result,
    disposition=RunDisposition.FAILED,
)
```

またはresult metadataに、

```json
{
  "run_disposition": "REVIEW_WAITING"
}
```

を持たせてもよい。

repository既存styleに合わせること。

---

# 13. Legacy Compatibility

既存Stageはmarker-based lifecycleを使用している。

historical Stageを全面書き換えない。

旧markerは、

```text
compatibility adapter
```

として残してよい。

ただしStage固有marker一覧をgeneric checkpoint coreのcanonical decision logicとして保持しない。

推奨：

```text
legacy Stage marker
        ↓
legacy adapter
        ↓
RunDisposition
        ↓
generic checkpoint lifecycle
```

とする。

---

# 14. Legacy Marker の扱い

最低限、

```text
existing historical review-waiting marker
existing historical complete-stop marker
```

は現在と同じ意味に変換できること。

ただし、

```text
Stage 3.9のmarkerをgeneric coreへ追加
```

する設計は禁止。

新しいStudyは最初からexplicit dispositionを使用する。

---

# 15. Stage 3.8 Historical Protection

Stage 3.8C-R1等のhistorical sourceは、legacy fingerprint / historical reproducibility保護のため無理に新APIへ移行しない。

今回変更対象に含めない。

```text
Stage 3.8 historical runner
    → legacy compatibility

Stage 3.9以降
    → explicit lifecycle disposition
```

という境界を維持する。

Stage 3.8 96k Productionの再実行は禁止。

---

# 16. Canonical Owner

作業開始時に既存実装を確認する。

最低限検索：

```text
CheckpointStore
LShadeCheckpointSession
reference_path
complete_study_run
_REVIEW_WAITING_MARKERS
WAITING_FOR_REVIEW
COMPLETE_STOP
finalize
run disposition
```

checkpoint lifecycleのcanonical ownerは引き続き、

```text
src/sawopt/io/
```

等のexisting canonical moduleとする。

Stage runnerにfinalization logicをコピーしない。

---

# 17. Test A — Runtime Reference

small fixture runで確認する。

実行途中：

```text
latest exists
final absent
```

の状態でresult artifactを生成する。

Acceptance：

```text
artifactがfinalをcurrent checkpointとして指さない
artifactが存在するruntime recovery stateまたはlogical streamを指す
```

こと。

---

# 18. Test B — REVIEW_WAITING Reference

REVIEW_WAITING状態で、

```text
latest
previous
```

を保持する。

確認：

```text
final absent
latest valid
previous valid if available
metadata disposition = REVIEW_WAITING
metadataが存在しないfinalをcurrent checkpointとして参照しない
```

---

# 19. Test C — COMPLETED Finalization

explicit dispositionを、

```text
COMPLETED
```

としてfinalizeする。

確認：

```text
final exists
latest absent
previous absent
temporary absent
metadata final_checkpoint points to existing final
```

---

# 20. Test D — FAILED Preservation

explicit disposition：

```text
FAILED
```

確認：

```text
latest preserved
previous preserved if available
final not created
```

failureによりrecovery dataが失われないこと。

---

# 21. Test E — UNKNOWN / Missing Disposition

explicit dispositionなし、またはunknown stateをfixtureで作る。

安全側behaviorとして、

```text
do not finalize
preserve latest / previous
```

となることを推奨する。

もし既存API互換性のため別behaviorを維持する必要がある場合は、

```text
legacy compatibility pathのみ
```

に限定し、新APIではexplicit dispositionを必須とする。

---

# 22. Test F — Legacy Marker Compatibility

historical fixtureを使用して、

```text
旧review waiting marker
        ↓
REVIEW_WAITING

旧complete marker
        ↓
既存semantics
```

へ変換されること。

Stage固有markerの意味を壊さない。

---

# 23. Test G — Resume Numerical Parity Regression

Stage 3.8.6本体ですでにPASSしている、

```text
uninterrupted
vs
checkpoint → resume
```

比較を再実行する。

確認対象：

```text
population
incumbent
objective
violation
RNG state
evaluation count
generation count
proposal count
duplicate count
termination point
```

今回のmetadata/lifecycle修正によってnumerical behaviorが変わっていないこと。

---

# 24. Fingerprint v2

Stage 3.8.5で導入したfingerprint v2を維持する。

今回の変更は主に、

```text
checkpoint lifecycle
artifact metadata
legacy adapter
```

である。

fingerprint dependency setを確認し、

```text
resume numerical semanticsに影響する変更
```

と、

```text
metadata/reporting-only change
```

を正しく分類する。

fingerprint schema v3は作らない。

---

# 25. Review Bundle

既存generic Review Bundle builderを使用する。

今回のCorrection用 bundle推奨名：

```text
stage3_8_6_checkpoint_retention_correction_review.zip
```

Stage固有ZIP logicを新設しない。

---

# 26. Review Bundle に含めるもの

最低限：

```text
REVIEW_ME.md
correction_summary.md
lifecycle_disposition_design.md
checkpoint_reference_validation.json
review_waiting_validation.json
completed_finalization_validation.json
failed_preservation_validation.json
legacy_marker_compatibility.json
resume_parity_validation.json
test_summary.md
review_bundle_validation.json
```

加えてgeneric builder標準の、

```text
Git HEAD
git status
scoped diff
relevant source snapshot
SHA-256 manifest
```

を含める。

---

# 27. Full Regression

targeted tests PASS後にrepository standard full suiteを実行する。

前回の実績は、

```text
273 passed
14 subtests passed
```

だが、実repositoryの現在baselineをsource of truthとする。

pre-existing failureは今回のfailureと区別する。

---

# 28. 長時間実験は禁止

今回必要なのは、

```text
unit tests
fixture integration tests
small deterministic resume test
full regression
```

のみ。

以下は実行しない。

```text
Stage 3.8 96k Production
Stage 3.8 8k
Stage 3.8 Pilot
64k / 96k / 128k / 256k optimizer rerun
Monte Carlo large sampling
Stage 3.9 production run
```

---

# 29. Repository 保護

禁止：

```text
git reset --hard
git clean -fd
unrelated user changes削除
無断stash
無断commit
無断push
history rewrite
```

pre-existing dirty stateを保持する。

今回変更だけをscoped diffとして記録する。

---

# 30. 今回やらないもの

scope外：

```text
checkpoint serializer全面刷新
new binary format
cloud storage integration
historical checkpoint bulk cleanup
Stage 3.8 source全面移行
Stage 3.9 topology implementation
ladder追加
impedance sweep
optimizer tuning
COM calibration
Stage 3.8 report generator整理
fingerprint schema更新
```

---

# 31. 推奨実行順

```text
Phase 0
Inventory / baseline
        ↓
Phase A
Checkpoint reference semantics修正
        ↓
Targeted tests
        ↓
Phase B
RunDisposition導入
        ↓
Phase C
Legacy marker adapter
        ↓
Targeted lifecycle tests
        ↓
Resume parity regression
        ↓
Full regression
        ↓
Correction review bundle
        ↓
STOP
```

---

# 32. Stop Gate

各Phase後にtargeted testを実行する。

failure時は次Phaseへ進まない。

testを通すために、

```text
optimizer behavior
RNG sequence
historical numerical result
checkpoint state payload
```

を変更してはならない。

---

# 33. Acceptance Criteria

## Checkpoint Reference

- runtime artifactがfuture `final` pathをcurrent checkpointとして指さない
- REVIEW_WAITING artifactが存在しないfinalを指さない
- COMPLETED artifactのfinal pathは実在する
- logical recovery streamの意味がdocumented

## Lifecycle

- explicit `COMPLETED` → finalize
- explicit `REVIEW_WAITING` → preserve latest / previous
- explicit `FAILED` → preserve latest / previous
- unknown stateで不用意にcheckpoint削除しない

## Architecture

- Stage-specific markerがgeneric core decision logicから除去またはlegacy adapterへ隔離
- Stage 3.9でgeneric checkpoint coreへmarkerを追加する必要がない
- Stage runnerにcheckpoint lifecycle codeをコピーしない

## Compatibility

- historical Stage marker behavior維持
- legacy checkpoint loader維持
- Stage 3.8 production artifact変更なし

## Numerical Integrity

- resume parity PASS
- RNG continuation PASS
- evaluation accounting PASS

## Regression

- targeted tests PASS
- full suite PASS
- long production rerunなし

---

# 34. Documentation

最低限更新する。

```text
checkpoint lifecycle
run disposition semantics
runtime checkpoint reference semantics
legacy marker compatibility
new study implementation guidance
```

特に以下を明記する。

> Checkpoint finalization is controlled by explicit run lifecycle disposition, not by absence of an error status.

> Runtime artifacts must not reference a future final checkpoint as though it already exists.

> New studies must use explicit lifecycle disposition rather than adding Stage-specific review markers to the generic checkpoint core.

---

# 35. REVIEW_ME.md

冒頭：

```text
Stage 3.8.6 Checkpoint Retention Correction:
PASS_AWAITING_REVIEW / FAIL_STOP
```

続けて：

```text
1. changed modules
2. checkpoint reference fix
3. runtime reference validation
4. explicit RunDisposition design
5. COMPLETED behavior
6. REVIEW_WAITING behavior
7. FAILED behavior
8. unknown-state safety
9. legacy marker compatibility
10. resume parity
11. fingerprint v2 impact
12. targeted tests
13. full regression
14. historical protection
15. known deferred items
```

を記載する。

---

# 36. 作業終了時の報告形式

```text
Stage 3.8.6 Checkpoint Retention Correction:
PASS_AWAITING_REVIEW / FAIL_STOP

Runtime checkpoint reference:
PASS / FAIL

REVIEW_WAITING reference:
PASS / FAIL

Explicit RunDisposition:
PASS / FAIL

COMPLETED finalization:
PASS / FAIL

REVIEW_WAITING preservation:
PASS / FAIL

FAILED preservation:
PASS / FAIL

Unknown-state safety:
PASS / FAIL

Legacy marker compatibility:
PASS / FAIL

Resume numerical parity:
PASS / FAIL

RNG continuation:
PASS / FAIL

Fingerprint v2 regression:
PASS / FAIL

Targeted tests:
PASS / FAIL

Full suite:
<result>

Long optimizer rerun:
NO

Stage 3.8 Production modification:
NO

Stage 3.9:
NOT STARTED

Review bundle:
<path>
```

その後停止すること。

---

# 37. Close 判定

このCorrectionで以下が確認できれば、Stage 3.8.6はclose可能とする。

```text
runtime checkpoint referenceが正確
+
checkpoint deletion/finalizationがexplicit lifecycle contract依存
+
Stage-specific marker依存がlegacy compatibilityへ隔離
+
resume numerical parity維持
+
full regression PASS
```

追加のproduction optimizer runは不要である。

今回のCorrection終了後はcheckpoint retention architectureをfreezeし、Stage 3.9以降はこのcanonical infrastructureを利用すること。
