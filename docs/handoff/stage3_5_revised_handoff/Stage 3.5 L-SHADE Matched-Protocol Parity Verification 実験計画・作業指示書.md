# Stage 3.5
# L-SHADE Matched-Protocol Parity Verification
## 実験計画・Codex作業指示書

## 1. 目的

Stage 3.5で観測されたhistorical L-SHADEとcurrent L-SHADEの差が、

- L-SHADEアルゴリズムそのものの差
- source lineage差
- checkpoint / adaptive-frequency-grid protocol差

のどれに起因するかを切り分ける。

現在もっとも有力な仮説は、

```text
RC6: historical provenance / protocol mismatch
```

である。

今回の実験では、historical runに可能な限りcheckpoint protocolを合わせた**16k bounded parity verificationを1回だけ実行**する。

この実験はoptimizer性能比較ではない。

目的は、

```text
4k / 8k adaptive-grid exchangeを除去した場合、
historical L-SHADE trajectoryを16kまで再現できるか
```

を確認することである。

---

# 2. 現在確立している事実

パイロット調査では以下が確認されている。

## 2.1 同一条件

```text
seed = 20260917
search space = S1
S1 hash = b4132c8f...
terminal population-schedule horizon = 64000
port impedance = 50 ohm
Git committed HEAD = 69a4df2...
```

historical/currentでこれらは一致している。

---

## 2.2 Source provenance

Git HEADは同じだがsource hashは異なる。

```text
historical:
bf1d9279...

current:
98ee63b2...
```

したがって、

```text
same Git HEAD != exact same source lineage
```

である。

historical側には完全なruntime/per-arm provenance manifestが存在しない。

---

# 3. 最重要発見

current parity runは、

```text
4k
8k
16k
```

でadaptive frequency-grid exchangeを行っている。

一方historical recordsは、

```text
16k
32k
64k
```

のcheckpoint sequenceを持ち、それぞれのrecordにfrequency-grid eventが存在する。

historical event自体にはbudget fieldが完全には残っていないため、実行前にhistorical semanticsを再確認すること。

---

## 3.1 4k以前の一致

current runの最初の4k exchange以前では、

```text
population trace:
3875 / 3875 exact match

archive trace:
3875 / 3875 exact match

best-so-far:
10 / 10 exact match
```

だった。

current runは4,000 unique evaluations時点で、

```text
60 critical frequencies
```

を追加し、

```text
grid version 1 -> 2
```

へ変更している。

したがって、現在確認されている最初のdivergenceは、

```text
optimizer event
```

ではなく、

```text
current-only 4k adaptive-frequency exchange
```

である。

---

# 4. 現在の解釈

4k exchange後はobjective grid自体が異なる。

そのため、それ以降の、

- candidate
- rank
- mutation selection
- archive state
- population evolution

をhistorical trajectoryと直接比較することはできない。

したがって現在の16k parity failureを、

```text
L-SHADE algorithm regression
```

として扱ってはならない。

また、

```text
current implementation is better/worse
```

という性能結論にも使用してはならない。

---

# 5. 今回の基本仮説

## H0 — protocol mismatch hypothesis

historical/currentの主要なtrajectory差は、

```text
adaptive frequency-grid exchange timing
```

によって生じている。

4k/8k exchangeを除去しhistorical protocolへ合わせれば、16kまでtrajectory parityが回復する。

---

## H1 — residual divergence hypothesis

checkpoint protocolを合わせても16k以前にtrajectoryがdivergeする。

この場合、

- source lineage
- runtime difference
- hidden configuration difference
- optimizer state difference
- historical provenance不足

のいずれかが残っている。

---

# 6. 今回変更してはいけないもの

以下は禁止。

```text
L-SHADE algorithm変更
mutation変更
crossover変更
archive rule変更
population schedule変更
objective変更
penalty変更
constraint変更
COM変更
search space変更
canonicalization変更
tolerance追加
seed変更
production budget拡張
```

historical source hashへ合わせるためにcurrent sourceを推測で修正することも禁止する。

今回行うのは、

```text
protocol reconstruction
+
matched-protocol diagnostic run
```

だけである。

---

# 7. Phase 0 — Historical Protocol Reconstruction

実験を開始する前に、historical B16000 recordを再確認する。

対象は最低限、

```text
runs/stage3_5_phase_c_revised/
arms/D_S1_LSHADE/
phase_c2/
trials/lshade/
center_outer_same/
seed20260917/
B16000.json
```

および関連artifact。

確認する。

### 必須確認項目

```text
seed
S1 identity/hash
terminal horizon
checkpoint sequence
adaptive-grid event count
adaptive-grid event ordering
grid version before/after
added frequency count
population size
best-so-far
population/archive traces
snapshot timing
```

特に、

```text
B16000.jsonが
16k exchangeの前を記録しているのか
exchange後を記録しているのか
```

を可能な限り特定する。

---

# 8. Historical semanticsが不明な場合

推測で進めてはならない。

以下のどれかを選ぶ。

```text
PRE_EXCHANGE
POST_EXCHANGE
UNKNOWN
```

`UNKNOWN` の場合でも、

```text
16k以前のtrajectory
```

を比較できるならdiagnostic run自体は可能。

ただし最終判定を、

```text
FULL_PARITY_PASS
```

とはしない。

---

# 9. Protocol Reconstruction Gate

実験実行前に以下を確認する。

current runnerで、

```text
terminal_horizon = 64000
diagnostic_stop = 16000
adaptive exchange checkpoint = 16000 only
```

を構成できること。

重要:

```text
checkpoints = [4000, 8000, 16000]
```

としてはならない。

---

# 10. 4k / 8k checkpoint禁止

今回、4k/8kを「観測用checkpoint」として追加することも禁止する。

理由:

現在の実装ではcheckpoint処理が、

```text
exchange_frequency_grid()
```

にcontrol-flow上隣接しており、単なる観測点ではない。

したがって、

```text
4k observation checkpoint
8k observation checkpoint
```

を追加すると、再び実験対象そのものを変えてしまう。

4k/8kに追加の観測が必要な場合でも、

```text
objective gridを変更しない
read-only telemetry
```

であることが既存コードから明確に保証できない限り追加しない。

今回の優先事項は観測量よりprotocol fidelityである。

---

# 11. Phase 1 — Preflight Verification

実際の16k optimizationを開始する前に、configurationだけを検証する。

以下をartifactとして保存する。

```text
protocol_manifest.json
provenance_manifest.json
```

---

## protocol_manifest

最低限、

```text
optimizer
seed
search space
S1 hash
port impedance
terminal horizon
diagnostic stop
requested checkpoints
adaptive exchange schedule
initial population
minimum population
population schedule identifier
canonicalization
```

を含める。

---

## provenance_manifest

最低限、

```text
Git HEAD
git status
source hash
Python version
NumPy version
runtime/library information
relevant source-file hashes
```

を記録する。

dirty worktreeを勝手にclean/resetしてはならない。

---

# 12. Preflight assertion

実験開始前に自動的に次を検証する。

```text
seed == 20260917

terminal_horizon == 64000

diagnostic_stop == 16000

4k exchange == disabled

8k exchange == disabled

16k exchange == enabled

S1 == historical S1

Zport == 50 ohm
```

1つでも成立しない場合、optimizationを開始してはならない。

---

# 13. テスト

既存コード変更がない場合:

Stage 3.5およびorchestration関連のtargeted testを実施する。

既存コードを変更した場合:

```text
targeted tests
+
full regression
```

を必須とする。

前回の参考値は、

```text
targeted: 35 passed
full regression: 174 passed
```

だが、今回のtest countが増減していても件数自体を固定条件にはしない。

失敗が0であることを確認する。

---

# 14. Observation-only instrumentation

既存telemetryだけでは比較不能な場合のみ、最小限のinstrumentation追加を許可する。

条件:

```text
optimizer stateを変更しない
RNGを消費しない
objectiveを再評価しない
gridを変更しない
candidate orderingを変更しない
```

単なるserialization / hashing / loggingに限定する。

instrumentation追加後はfull regressionを行う。

optimizer behaviorへ影響する可能性がある場合はSolへエスカレーションし、実験を開始しない。

---

# 15. Phase 2 — Matched-Protocol 16k Run

Preflightを通過したら、1回だけ実行する。

設定:

```text
optimizer:
L-SHADE

seed:
20260917

search space:
S1

impedance:
50 ohm

terminal population horizon:
64000

diagnostic stop:
16000

adaptive frequency-grid exchanges:
16k only
```

---

# 16. 実験回数

今回のproduction-level optimizationは、

```text
1 run only
```

とする。

seed追加は禁止。

32k/64kまで延長しない。

matched 16kがPASSしたとしても、自動的に64kへ進めない。

---

# 17. 長時間run policy

16k runが長時間runに該当する場合は、既存プロジェクトのdetached orchestration policyに従う。

同期shellで長時間待機しない。

既存の、

```text
python -m sawopt.orchestration.cli launch
```

系のproduction launcherを使用する。

ただし、今回のrunが短時間diagnosticとして既存policy上同期実行可能なら、その既存運用を優先する。

新しい実行基盤は作らない。

---

# 18. Phase 3 — Parity Comparison

run完了後、historical B16000と比較する。

比較は以下の3層に分ける。

---

## Layer A — Protocol parity

確認:

```text
seed
S1
terminal horizon
effective exchange timing
frequency count
grid version
population schedule
population size
```

特に、

```text
4k/8kでgridがversion 1のまま
```

であることを確認する。

---

## Layer B — Trajectory parity

可能な範囲で、

```text
population trace
archive trace
best-so-far trace
```

をexact comparisonする。

最低限、

```text
16k exchange直前
```

まで比較する。

---

## Layer C — Endpoint parity

historical snapshot semanticsが判明している場合、

```text
decoded best candidate
validated rank tuple
common validation metrics
population size
grid state
```

を同じsemantic pointで比較する。

---

# 19. Numeric tolerance

今回、新しい数値toleranceを導入してはならない。

これまでのparity方針を維持し、

```text
exact candidate/rank/metric/trace match
```

を原則とする。

非常に小さなfloating-point差だけが発生しても、その場で許容誤差を設定してPASSにしてはならない。

その場合は、

```text
PARITY_FAILED_NEEDS_REVIEW
```

として扱う。

---

# 20. Telemetry counter

以下は補助情報であり、parity gateそのものには使用しない。

例:

```text
objective_calls
cache_hits
cache_hit_rate
duplicate decoded attempts
wall time
```

instrumentationやcache accounting差によって異なる可能性がある。

semantic trajectoryが一致しているのにtelemetry counterだけが異なる場合、それだけを理由にalgorithm parityをFAILとしてはならない。

ただし差は必ず記録する。

---

# 21. 結果分類

以下のいずれかへ分類する。

## A — PARITY_PASS_MATCHED_PROTOCOL

条件:

```text
protocol parity = PASS
trajectory through 16k = exact match
endpoint semantics = comparable
endpoint = exact match
```

解釈:

RC6 protocol mismatchが主要原因だったことを強く支持する。

L-SHADE algorithm regressionを支持しない。

---

## B — TRAJECTORY_PASS_ENDPOINT_INCONCLUSIVE

条件:

16kまでのtrajectoryは一致するが、historical snapshot semantics不足などによりendpointを厳密比較できない。

解釈:

optimizer trajectory parityは強く支持されるが、完全provenance parityとは断定しない。

---

## C — PARITY_FAIL_PRE16K

matched protocolでも16k exchange以前にdivergeする。

これは重要な結果。

直ちにproduction experimentを止める。

---

## D — PARITY_FAIL_AT_EXCHANGE

16k exchange以前は一致するが、16k frequency-grid exchangeによってdivergeする。

exchange semantics / implementation / source lineageを次の調査対象とする。

---

## E — PROVENANCE_INCOMPLETE_NO_RUN

historical protocolを十分再構成できず、matched runの意味を保証できない。

この場合run自体を行わない。

---

# 22. FAIL時のFirst-Divergence Trace

CまたはDの場合、新しい長時間runを追加してはならない。

今回のrunから取得済みのevidenceを使用し、

```text
first_divergence_trace.md
```

を作る。

記録:

```text
last matching evaluation/state
first differing evaluation/state
population index if available
archive state
best-so-far
grid version
RNG/state hash if already available
objective state
checkpoint/event relation
```

新たなoptimizer変更はしない。

---

# 23. Source-lineage調査

matched protocolでもdivergeした場合、

```text
historical source hash != current source hash
```

が再び重要になる。

ただし、

```text
historical sourceを推測して復元する
```

ことは禁止。

まず、

- recoverable historical files
- archived review bundle
- Git object/history
- recorded diff
- run artifacts

からread-only reconstructionを行う。

historical dirty sourceを正確に復元できない場合は、その事実を明記する。

---

# 24. Sol Escalation Policy

既存のLuna root → Sol on-demand policyをそのまま使用する。

通常の、

```text
config作成
run execution
comparison
artifact作成
test
```

はLunaが実施する。

---

# 25. Mandatory Sol escalation

以下の場合、GPT-5.6 Solへエスカレーションする。

### 実験前

historical protocolに複数の合理的解釈があり、どのconfigurationでrunするか判断が必要。

### 実験後

```text
PARITY_FAIL_PRE16K
PARITY_FAIL_AT_EXCHANGE
```

になった。

### その他

- source変更を検討する必要が生じた
- tolerance導入を検討した
- optimizer変更を検討した
- 16kより長い再実験を検討した
- current/historicalのどちらを正とするか判断が必要
- result interpretationに複数の合理的解釈がある

---

# 26. Sol escalation方式

既存policy通り、

```text
model = gpt-5.6-sol
fork_context = false
```

を優先する。

Escalation Packetを作成する。

Solにはコード実装ではなく、

```text
result interpretation
root-cause classification
next diagnostic decision
```

だけを依頼する。

Lunaが実装担当を維持する。

---

# 27. PASS時のSol呼び出し

結果が明確に、

```text
PARITY_PASS_MATCHED_PROTOCOL
```

であり、解釈に曖昧性がない場合は、Codex内部のSolを追加で呼ぶ必要はない。

そのままChatGPT Sol review gateへ進む。

不要なSol使用を避ける。

---

# 28. Phase D禁止

今回の作業ではPhase Dを開始しない。

結果が完全PASSでも、

```text
Phase D launch
production optimization
32k/64k extension
```

を自動的に行ってはならない。

必ずChatGPT Solレビューで停止する。

---

# 29. 実験結果artifact

推奨ディレクトリ:

```text
runs/
└─ stage3_5_lshade_matched_protocol_16k/
   ├─ manifests/
   │  ├─ provenance_manifest.json
   │  └─ protocol_manifest.json
   ├─ results/
   │  ├─ matched_protocol_parity.json
   │  ├─ trajectory_comparison.json
   │  └─ endpoint_comparison.json
   ├─ logs/
   └─ reports/
      ├─ stage3_5_matched_protocol_review.md
      ├─ first_divergence_trace.md        # FAIL時のみ
      └─ escalation_log.md                # escalation時
```

既存project conventionがある場合、それに合わせて調整してよい。

review bundleはAGENTS.mdの既存規則通りrepository rootの、

```text
artifacts/review_bundles/
```

へ作成する。

---

# 30. matched_protocol_parity.json

最低限以下を含める。

```text
status
historical_record
current_record
seed
S1_hash
historical_source_hash
current_source_hash
terminal_horizon
diagnostic_stop
historical_checkpoint_protocol
current_checkpoint_protocol
exchange_events
pre_exchange_parity
trajectory_parity
endpoint_parity
telemetry_differences
leading_root_cause
source_change_justified
next_action
```

---

# 31. 最終レポート

作成:

```text
stage3_5_matched_protocol_review.md
```

構成:

```text
# Stage 3.5 Matched-Protocol Parity Review

## 1. Executive Summary

## 2. Historical Protocol Reconstruction

## 3. Current Protocol

## 4. Provenance Comparison

## 5. Preflight Verification

## 6. Run Configuration

## 7. Protocol Parity

## 8. Trajectory Parity

## 9. Endpoint Parity

## 10. Telemetry Differences

## 11. First Divergence
(if applicable)

## 12. Root-Cause Assessment

## 13. Sol Escalations
(if applicable)

## 14. Stage 3.5 Recommendation

## 15. Phase D Readiness
```

---

# 32. Root-Cause Assessment

既存RC分類を維持する。

今回の主目的は、

```text
RC6 historical provenance/protocol mismatch
```

を支持または棄却すること。

証拠なしに別RCへ変更しない。

---

# 33. Phase D Readiness

以下から1つ選択。

### READY_FOR_CHAT_SOL_REVIEW

matched protocol parityが十分確認された。

ただしPhase Dはまだ開始しない。

---

### NEEDS_ROOT_CAUSE_REVIEW

matched protocolでもdivergenceした。

Sol escalation結果を含めてChat Solへ戻す。

---

### PROVENANCE_BLOCKED

historical provenance不足により有効なparity runを構成できなかった。

---

# 34. この実験で答える質問

最終的に以下へ答える。

> 4k/8k adaptive-frequency exchangeを除去し、
> historical checkpoint protocolへ合わせると、
> current L-SHADEはhistorical L-SHADE trajectoryを
> 16kまで再現するか？

この質問以外へ実験目的を拡張しない。

---

# 35. 作業完了条件

以下を満たしたら停止する。

1. Historical protocol reconstruction完了
2. Preflight完了
3. 必要なtests PASS
4. matched-protocol 16k runを最大1回実行
5. parity comparison完了
6. 必要ならSol escalation完了
7. final report作成
8. review bundle作成

その後、

```text
STOP FOR CHATGPT SOL REVIEW
```

とする。

Phase Dへ自動的に進まない。

---

# 36. Codexへの最終指示

今回の目的はL-SHADEを修正することではない。

目的は、

```text
historical/current comparisonから
checkpoint/grid protocol confounderを除去し、
16kまでのtrajectory parityを検証する
```

ことである。

現在の証拠ではoptimizer source変更は正当化されていない。

したがって、

```text
まず再現性を証明する。
再現性が失敗した場合のみ原因を特定する。
原因特定前に修正しない。
```

という順序を厳守すること。