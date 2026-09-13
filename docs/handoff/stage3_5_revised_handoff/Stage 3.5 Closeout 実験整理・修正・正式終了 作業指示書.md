# Stage 3.5 Closeout
## 実験整理・修正・正式終了 作業指示書

## 1. 目的

Stage 3.5の技術的調査は完了した。

matched-protocol検証により、historical/current間で観測されていたL-SHADE trajectory差について、

```text
RC6: historical/current protocol mismatch
```

が主要因であることを強く支持する結果が得られた。

今回の作業目的は新しい最適化実験ではない。

以下を完了させ、Stage 3.5を正式にcloseする。

1. Stage 3.5の最終結論を固定する
2. orchestration status不整合を修正する
3. misleading / stale artifactを整理する
4. `historical_protocol` 関連エラーを解消する
5. test evidenceを明示的に保存する
6. telemetry差を必要な範囲で整理する
7. Stage 3.5最終close reportを作成する
8. 次フェーズへ渡す前提条件を明文化する

---

# 2. Stage 3.5で確定済みの技術的結論

以下は原則として再検証対象ではない。

matched-protocol runでは、

```text
4k adaptive-grid exchange = disabled
8k adaptive-grid exchange = disabled
16k adaptive-grid exchange = enabled
terminal population horizon = 64000
diagnostic stop = 16000
seed = 20260917
search space = S1
Zport = 50 ohm
```

というhistorical protocolに合わせた条件を使用した。

その結果、16k pre-exchangeまで、

```text
population trace:
15,875 / 15,875 exact match

archive trace:
15,875 / 15,875 exact match

best-so-far trace:
14 / 14 exact match
```

が得られた。

さらに、

```text
best design
validated rank tuple
validation metrics
16k exchange frequency set
```

も一致した。

したがって、Stage 3.5で以前観測されたtrajectory差を、

```text
L-SHADE algorithm regression
```

で説明する証拠はない。

主要因は、

```text
4k / 8k adaptive-frequency-grid exchangeを含む
current protocolとhistorical protocolとの差
```

で説明できる。

---

# 3. Closeoutで変更してはいけない結論

以下のように結論を書き換えてはならない。

```text
L-SHADEにアルゴリズム上の不具合があった

Legacy-DEとL-SHADEの差はoptimizer実装変更で説明できる

source hash差がtrajectory差の主要因だった
```

今回のevidenceはこれらを支持していない。

Stage 3.5の正式なroot-cause表現は、過度に断定せず、

```text
RC6_PROTOCOL_MISMATCH_STRONGLY_SUPPORTED
```

または既存分類規則に合わせた同等表現とする。

既存プロジェクトですでに

```text
RC6_PROTOCOL_MISMATCH_SUPPORTED
```

を正式名称として使っている場合は、名称を不用意に変更せずそれを維持してよい。

---

# 4. 今回禁止する実験

Closeout中は以下を実行してはならない。

```text
新しい16k optimization
32k extension
64k extension
追加seed
Legacy-DE再実験
L-SHADE再実験
search-space変更
objective変更
optimizer変更
COM変更
Phase D開始
```

Stage 3.5の科学的結論をさらに強くする目的だけで追加計算を行わない。

現在のevidenceでcloseする。

---

# 5. Task A — 現状のartifact監査

まずStage 3.5 matched-protocol成果物をread-onlyで監査する。

最低限確認する。

```text
protocol_manifest
provenance_manifest
matched_protocol_parity
trajectory_comparison
endpoint_comparison
final review
status.json
stderr/stdout
first_divergence_trace.md
test-related artifacts
```

以下を一覧化する。

```text
valid artifact
stale artifact
misleading artifact
missing artifact
runtime-state inconsistency
```

この監査段階では変更しない。

---

# 6. Task B — status.json不整合の原因修正

現在、実験成果物が正常に完成しているにもかかわらず、

```text
state = RUNNING
optimizer_state = RUNNING
exit_code = 1
resume_count = 1
resume_requested = true
```

等の不整合が残っている。

また、実行途中に、

```text
'historical_protocol'
```

に関連するエラーが記録されている。

これはStage 3.5の科学的結果そのものとは別の、

```text
orchestration / report-generation / finalization defect
```

として扱う。

---

## 6.1 原因特定

以下を調査する。

```text
どの処理で historical_protocol KeyError が発生したか

最初のprocess exit_code=1がどこから発生したか

resume後に成果物が完成したにもかかわらず、
なぜstatusがSUCCESS/COMPLETEDへ遷移しなかったか

finalizationがidempotentか

resume pathとfresh-run pathでstatus更新ロジックが異ならないか
```

推測でstatusだけを書き換えて終了してはならない。

---

# 7. status lifecycleの期待仕様

正常終了時には、プロジェクト既存の命名規則に従い、

```text
COMPLETED
SUCCESS
FINISHED
```

等の正式なterminal stateのいずれかになること。

既存schemaを確認し、勝手に新しいstate名を追加しない。

また正常終了時に、

```text
exit_code = 0
running = false
resume_requested = false
```

等、既存schema上必要な値が正しく確定すること。

---

# 8. Finalization修正の原則

修正はgeneral fixとして行う。

今回のrunだけを特別扱いするhard-codeは禁止。

悪い例:

```text
if run_name == "stage3_5_lshade_matched_protocol_16k":
    status = "COMPLETED"
```

禁止。

必要なら、

```text
successful artifact completion
process return state
resume completion
report generation
```

間のstatus lifecycleを一般化して修正する。

---

# 9. historical_protocol KeyError

`historical_protocol` が必須fieldなのかoptional fieldなのかをschema/生成経路から確認する。

以下のどちらかを明確にする。

### Case A

必須fieldなのにwriter側が生成していなかった。

→ writer / schema validationを修正する。

### Case B

optional fieldなのにconsumer側が必須扱いしていた。

→ defensive read / optional handlingを修正する。

どちらか不明なまま、

```python
try:
    ...
except KeyError:
    pass
```

だけで隠してはならない。

---

# 10. Task C — first_divergence_traceの整理

matched-protocolの正式結果は、

```text
16k pre-exchangeまでexact trajectory parity
```

である。

したがって、PASS runで存在する `first_divergence_trace.md` が、

```text
16kでfirst divergence
```

と誤認させる内容になっている場合は修正する。

---

## 10.1 正しいsemantic

historical B16000がpre-exchange snapshotで終了し、

current telemetryが16k exchange後のeventまで含んでいるため、

```text
historical trace ends
current trace has additional post-snapshot event
```

という構造を、

```text
trajectory divergence
```

として扱ってはならない。

---

## 10.2 修正方針

理想は、

```text
parity PASSの場合:
first_divergence_trace.mdを生成しない
```

こと。

ただし既存review schema上ファイルが必須なら、

```text
No pre-exchange divergence detected.

The apparent difference after the historical snapshot boundary
is a post-snapshot event and is not classified as trajectory divergence.
```

という明示的な内容にする。

---

# 11. Task D — parity判定ロジックの境界修正

必要なら比較ロジックを修正し、

```text
snapshot semantic boundary
```

を明示的に扱う。

比較範囲は、

```text
historical/current双方で意味的に比較可能な区間
```

に限定する。

一方にしか存在しないpost-snapshot eventを、

```text
first divergence
```

として自動分類してはならない。

---

# 12. Task E — objective_calls差の確認

matched-protocol結果では、

```text
current objective_calls    = historical + 126
```

という差があり、

```text
126
```

はinitial population sizeと一致している。

一方、

```text
cache_hits
unique-evaluation trajectory
population/archive trajectory
best trajectory
endpoint
```

は一致している。

この差は現時点では、

```text
telemetry / accounting difference
```

である可能性が高い。

---

## 12.1 今回行う範囲

コード変更前に、

```text
初期population評価をどの地点からcounterへ含めるか
historical/currentでcounter初期化位置が違うか
resume/reportingで二重計上していないか
```

を静的に確認する。

---

## 12.2 修正条件

原因が明白かつ単純なcounter bugであり、

```text
optimizer trajectory
objective semantics
cache semantics
```

へ影響しない場合のみ修正してよい。

それ以外は、

```text
Known telemetry accounting difference
```

としてclose reportへ残す。

この差を解消するためのoptimization再実験は禁止する。

---

# 13. Sol escalation条件

Closeout作業も既存の、

```text
Luna root → Sol on-demand escalation
```

policyに従う。

通常のcleanup、tests、report更新はLunaが行う。

---

## Mandatory Sol escalation

以下の場合のみSolへ相談する。

```text
status lifecycle修正がorchestration architectureへ波及する

historical_protocolの正しいschema解釈が複数存在する

parity判定のsemantic boundary変更が
過去の他実験の判定結果を変える可能性がある

objective_calls差が単なるtelemetry差ではなく
optimizer挙動へ影響している疑いが生じた

Stage 3.5のroot-cause結論を変更する必要が生じた
```

Solには実装ではなく判断レビューを依頼する。

---

# 14. Task F — Regression Tests

修正後、少なくとも以下をテストする。

## 14.1 Status lifecycle

- fresh successful run
- resumed successful run
- genuine failed run

それぞれが正しいterminal stateになること。

---

## 14.2 historical_protocol handling

- field present
- field absent but optional
- malformed input

既存schemaに従い正しく処理されること。

---

## 14.3 Parity comparison

以下のfixtureを用意できる場合はテストする。

### Exact match

→ PASS

### Real divergence before boundary

→ first divergenceを検出

### Historical snapshot ends before current post-event

→ trajectory divergenceとして扱わない

---

# 15. Test範囲

今回orchestration/comparisonコードへ変更が入るため、

```text
targeted tests
+
full regression suite
```

を実行する。

件数そのものを固定しない。

必須条件:

```text
0 failed
```

---

# 16. Test evidence保存

今回のcloseout review bundleには必ずtest証跡を含める。

推奨:

```text
test_summary.json
```

または既存プロジェクト形式。

最低限、

```text
command
timestamp
targeted passed/failed
full suite passed/failed
exit code
```

を記録する。

単にfinal reportへ、

```text
tests passed
```

と書くだけでは不十分。

---

# 17. Task G — Stage 3.5 Final Decision Record

Stage 3.5の最終decision recordを作成する。

例:

```text
stage3_5_final_decision.md
```

既存のdecision registry形式があるならそれを使用する。

---

## 必須内容

### Question

なぜhistorical/current L-SHADEで結果傾向が変わったのか。

### Evidence

matched protocolで、

```text
population 15,875 / 15,875 exact
archive 15,875 / 15,875 exact
best trace 14 / 14 exact
best design exact
rank exact
16k frequency exchange exact
```

が成立。

### Conclusion

主要因:

```text
checkpoint / adaptive-frequency-grid protocol mismatch
```

### Rejected hypothesis

```text
L-SHADE algorithm regression
```

は今回のevidenceでは支持されない。

### Caveat

historical/current source hashは一致しないが、

matched protocolでtrajectoryが完全再現されたため、

```text
source differenceが今回のtrajectory divergenceの主要因
```

という仮説も支持されない。

---

# 18. Stage 3.5で今後固定する比較ルール

重要な再発防止ルールとして、以下をプロジェクト文書へ反映する。

```text
optimizer performance comparisonでは、
adaptive frequency-grid exchange scheduleを含む
evaluation protocolを一致させること。
```

特に、

```text
4k / 8k / 16k protocol
```

と

```text
16k / 32k / 64k protocol
```

の結果を、

```text
same-budget optimizer comparison
```

として直接比較してはならない。

---

# 19. Checkpointの意味を明文化

今後は、

```text
checkpoint
```

という名称を、

```text
単なる観測点
```

と誤解しないようにする。

現在の実装ではcheckpointが、

```text
adaptive frequency-grid exchange
```

などalgorithm/environment stateの変更を伴う場合がある。

可能なら文書上、

```text
observation checkpoint
adaptive exchange checkpoint
```

などを区別する。

今回は大規模API renameまでは行わなくてよい。

少なくともdocumentationへ意味を残す。

---

# 20. Task H — Stage 3.5 Final Report

作成:

```text
stage3_5_final_closeout_review.md
```

推奨構成:

```text
# Stage 3.5 Final Closeout Review

## 1. Executive Summary

## 2. Original Question

## 3. Investigation Timeline

## 4. Historical vs Current Protocol Difference

## 5. Matched-Protocol Verification

## 6. Exact-Parity Evidence

## 7. Root-Cause Conclusion

## 8. Rejected Hypotheses

## 9. Source-Provenance Caveat

## 10. Telemetry Accounting Difference

## 11. Orchestration / Artifact Issues Found

## 12. Fixes Applied

## 13. Regression Test Results

## 14. Sol Escalations
(if any)

## 15. Remaining Known Limitations

## 16. Stage 3.5 Final Status

## 17. Rules Carried Forward

## 18. Next-Stage Readiness
```

---

# 21. Final status

最終reportでは以下のどちらかを選択する。

## STAGE_3_5_CLOSED

条件:

```text
matched-protocol result preserved
status/finalization defect fixed
misleading divergence artifact fixed
tests PASS
no unresolved issue capable of changing Stage 3.5 conclusion
```

---

## STAGE_3_5_CLOSE_BLOCKED

以下の場合のみ。

```text
cleanup中にparity結論を覆す証拠が見つかった

status bugがoptimizer/result integrityへ影響していた

comparison logicそのものがexact parityを誤判定していた
```

単なるtelemetry counter差だけではBLOCKEDにしない。

---

# 22. Close時の正式結論

問題がなければ、以下の趣旨でcloseする。

```text
Stage 3.5 is closed.

The apparent historical/current L-SHADE trajectory discrepancy
was caused primarily by a protocol mismatch in adaptive
frequency-grid exchange timing.

When the current run was executed under the matched historical
protocol, the pre-exchange trajectory through 16k and the
validated endpoint matched exactly.

No evidence from Stage 3.5 justifies a change to the L-SHADE
algorithm.
```

プロジェクトの既存言語・文体に合わせて表現調整してよい。

---

# 23. Phase Dについて

Stage 3.5をcloseしても、

```text
Phase Dを自動開始してはならない。
```

今回の作業はcloseoutまで。

最終成果物をChatGPT Solレビューへ返す。

そのレビュー後に次フェーズを計画する。

---

# 24. Review bundle

closeout完了後、レビュー用bundleを作成する。

推奨内容:

```text
stage3_5_closeout_review/
├─ stage3_5_final_closeout_review.md
├─ stage3_5_final_decision.md
├─ test_summary.json
├─ protocol_manifest.json
├─ provenance_manifest.json
├─ matched_protocol_parity.json
├─ trajectory_comparison.json
├─ endpoint_comparison.json
├─ status_before.json
├─ status_after.json
├─ relevant_error_log.txt
├─ first_divergence_trace.md
├─ escalation_log.md          # 使用時のみ
└─ changed_files_summary.md
```

既存review bundle規則がある場合はそちらを優先する。

---

# 25. changed_files_summary

今回closeoutで変更した、

```text
source
tests
documentation
report
status handling
comparison logic
```

を一覧化する。

各変更について、

```text
変更理由
behavioral impact
optimizer behaviorへの影響有無
```

を記録する。

---

# 26. Git / provenance

closeout開始時と完了時に、

```text
git status
git diff --stat
Git HEAD
```

を記録する。

勝手に過去のdirty worktreeをclean/resetしない。

今回の修正だけを識別できる形にする。

---

# 27. 完了条件

以下をすべて満たしたらStage 3.5をcloseする。

1. matched-protocolの技術的結論を再確認
2. status lifecycle不整合のroot causeを特定
3. 必要なgeneral fixを実施
4. `historical_protocol` errorを解消
5. PASS runのmisleading divergence artifactを解消
6. telemetry差を確認・文書化
7. targeted tests PASS
8. full regression PASS
9. explicit test evidence保存
10. final decision record作成
11. final closeout report作成
12. review bundle作成
13. final statusを明示

最後に、

```text
STAGE_3_5_CLOSED
```

または

```text
STAGE_3_5_CLOSE_BLOCKED
```

を明記する。

---

# 28. 最終停止条件

```text
STAGE_3_5_CLOSED
```

になった場合でも、次の実験を開始しない。

以下で停止する。

```text
STOP FOR CHATGPT SOL REVIEW
```

次フェーズの計画は、closeout成果物のレビュー後に別途決定する。

---

# 29. Codexへの最終指示

今回の作業は、

```text
Stage 3.5の結論を変更するための追加研究
```

ではない。

目的は、

```text
既に得られたexact-parity evidenceを正式なStage結論として固定し、
その結論を安全に引き継げる状態へプロジェクトを整理する
```

ことである。

したがって、

```text
新しいoptimizer実験をしない
optimizerを変更しない
結果を良く見せるために判定条件を緩和しない
cleanup defectとscientific resultを混同しない
```

こと。

cleanup中にStage 3.5の科学的結論へ影響する新しい証拠が見つかった場合のみ作業を停止し、Solへエスカレーションした上で `STAGE_3_5_CLOSE_BLOCKED` として報告すること。