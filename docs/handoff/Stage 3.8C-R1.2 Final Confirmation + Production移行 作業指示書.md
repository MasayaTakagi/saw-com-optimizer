# Stage 3.8C-R1.2 Final Confirmation
## Minimal Reproducibility Check → Production Transition

## 1. 目的

Stage 3.8C-R1.2では、

- geometry-first ranking correction
- distribution-preserving initializer
- independent-uniform rejection sampling
- geometry-valid initial population
- physics evaluation
- counter accounting
- fixed-design sanity
- GPT-6 Sol routing
- full test suite

が正常であることを確認済みである。

残っている問題は、Pilot実行後にreport/review関連のsource変更が入ったため、

**Pilot実行時source fingerprintと現在の最終source fingerprintが一致していない**

ことである。

今回の作業では、詳細な再現性調査は行わない。

現在の最終sourceをfreezeした状態で、R1.2 Pilotを1回だけcold rerunし、

**Productionで使用するsource/configそのものが正常に動作すること**

だけを確認する。

この確認がPASSした場合は、追加のPilotやMonte Carlo検証を行わず、Stage 3.8C Productionへ進む。

---

# 2. 今回の基本方針

今回の再現性確認は**最小限**とする。

目的は、

```text
過去Pilotを完全再現すること
```

ではなく、

```text
Productionで使用する最終source/configが、
すでに確認したR1.2 semanticsを維持したまま正常に動作すること
```

の確認である。

以下は要求しない。

- 過去Pilotとの数値完全一致
- byte-for-byte artifact一致
- elapsed time一致
- ZIP timestamp一致
- R1/R1.1/R1.2詳細比較の再実施
- Monte Carlo distribution validationの再実施
- GPT-6 Solによる追加レビュー
- historical artifact整理
- repository全体の完全clean化
- backend内部model identityの追加確認

---

# 3. 新しいR1.3は作らない

今回の作業は新しいアルゴリズム変更ではない。

したがって、

```text
Stage 3.8C-R1.3
```

のような新しいrevisionを作成しない。

名称は、

```text
Stage 3.8C-R1.2 Final Confirmation
```

とする。

---

# 4. Source Freeze

Final Pilot開始前に、Productionで使用予定のsource/configを確定する。

最低限以下を記録する。

```text
git rev-parse HEAD
git branch --show-current
git status --short
```

さらに、

```text
source fingerprint
config fingerprint
```

または既存のcombined fingerprintを計算・保存する。

この時点以降、Final Pilot完了まで、

- optimizer code
- COM code
- geometry logic
- Stage 3.8 study code
- initializer
- config
- objective
- topology
- material profile

を変更しない。

---

# 5. 許容する変更

Final Pilot後、Production開始前に変更してよいのは原則として、

- status marker
- execution manifest
- report
- README
- review summary
- Production enable flag/config

など、計算意味論に影響しないものだけとする。

ただしProduction fingerprint対象ファイルを変更すると再度gateが閉じる場合は、不要な変更を避ける。

---

# 6. Final Pilot条件

R1.2 Pilotと同じ条件を使用する。

## Materials

```text
M0
MLIT
```

## Topologies

```text
T0
T1
T2
```

計6 cells。

## Seed

```text
20260917
```

## Budget

```text
256 unique optimizer evaluations / cell
```

## Initializer

```text
independent-uniform proposal
→ canonicalization
→ geometry validation
→ reject/resample
```

R1.1 conditional initializerへ戻してはならない。

---

# 7. Final Pilotで確認する項目

今回は以下だけをMandatory Gateとする。

## Gate 1 — Source/config identity

Pilot実行時fingerprintと、Production予定source/configのfingerprintが一致していること。

```text
pilot_fingerprint == production_candidate_fingerprint
```

---

## Gate 2 — Pilot completion

```text
6 / 6 cells completed
```

---

## Gate 3 — Initial population

各cellで、

```text
requested population == accepted population
```

かつ、

```text
100% geometry-valid
```

であること。

rejection fractionの大小はFAIL条件にしない。

---

## Gate 4 — Physics

各6セルについて、

```text
successful physics evaluations > 0
solved frequency points > 0
```

を満たす。

physics failureが異常発生していないこと。

---

## Gate 5 — Finite results

各cellについて、

- search-grid metrics finite
- common-grid metrics finite

であること。

---

## Gate 6 — Counter accounting

既存のcounter consistency checkをPASSすること。

---

## Gate 7 — Fixed-design sanity

```text
6 / 6 PASS
```

を要求する。

---

## Gate 8 — Tests

既存test suiteがPASSすること。

新しい大規模テスト追加は不要。

---

# 8. 今回確認しなくてよいもの

以下はR1.2ですでに確認済みなので再検証不要。

### Distribution validation

- KS comparison
- Monte Carlo reference
- R1/R1.1/R1.2 distribution comparison
- integer sampling bias解析

### Performance interpretation

- topology ranking
- material ranking
- Production candidate ranking
- seed consistency

### Sol review

GPT-6 Sol routingの既存regression testだけ維持する。

新しいSolレビュー呼び出しは不要。

---

# 9. Pilot結果の数値一致を要求しない

R1.2 previous PilotとFinal Pilotで、

- incumbent design
- objective value
- violation
- runtime

が完全一致することは要求しない。

同じseedでも、execution environmentや細かな実装条件によって差が発生する可能性がある。

重要なのは、

**同じ計算意味論で正常に探索が成立すること**

である。

---

# 10. Final Pilot PASS条件

以下すべてを満たせばPASS。

```text
source/config fingerprint match
AND
6/6 cells completed
AND
initial populations geometry-valid
AND
physics evaluations valid
AND
finite metrics
AND
counter accounting PASS
AND
fixed-design sanity 6/6
AND
test suite PASS
```

PASS時は、

```text
STAGE3_8C_R1_2_FINAL_CONFIRMATION_PASS
```

markerを作成する。

---

# 11. FAIL条件

以下の場合はProductionを開始せず停止する。

- fingerprint mismatch
- cell未完了
- initial population生成失敗
- physics evaluation不成立
- NaN / Inf
- counter inconsistency
- fixed-design sanity FAIL
- test suite FAIL

FAIL時は、

```text
STAGE3_8C_R1_2_FINAL_CONFIRMATION_FAIL_STOP
```

を作成する。

---

# 12. PASS後のProduction移行

Final ConfirmationがPASSした場合、

**追加のChatGPTレビュー待ちは不要とする。**

そのままStage 3.8C Productionを開始してよい。

ただしFinal Confirmation PASSの証跡を保存してから開始する。

---

# 13. Production条件

Production規模：

```text
8,000 evaluations / cell
× 2 seeds
× 6 cells
= 96,000 evaluations
```

既存のProduction設定を使用する。

変更禁止：

- optimizer
- initializer
- bounds
- COM parameters
- topology definitions
- objective
- geometry constraints
- manufacturing limits
- common validation grid
- impedance condition

---

# 14. Production開始時のfingerprint protection

Production launcherはFinal Pilotで使用したsource/config fingerprintと一致することを確認する。

```text
production_fingerprint
==
final_confirmation_fingerprint
```

一致しない場合は自動停止する。

fingerprint mismatchを回避するためにgateを無効化してはならない。

---

# 15. Production Seeds

既存Production configで指定済みの2 seedsを使用する。

Final Pilot seed `20260917` とProduction seedsの扱いは既存計画を維持する。

今回のFinal Confirmationを理由にseed構成を変更しない。

---

# 16. Production実行中

Productionでは通常のcheckpoint/loggingを使用する。

ただし今回の作業で、

- checkpoint方式変更
- optimizer restart logic変更
- asynchronous orchestration変更

は行わない。

既存の安定した実行pathを使用する。

---

# 17. Production完了時

96k Production完了後は、自動でStage 3.9へ進まない。

Production結果をまとめてreview bundleを作成し停止する。

---

# 18. Production review bundle

推奨：

```text
stage3_8c_production_review.zip
```

最低限以下を含める。

## Summary

```text
REVIEW_ME.md
stage3_8c_production_summary.md
stage3_8c_production_gate.json
test_summary.md
```

## Production results

```text
stage3_8c_production_results.csv
stage3_8c_all_seed_results.csv
stage3_8c_seed_comparison.csv
stage3_8c_counter_accounting.csv
stage3_8c_validated_responses.csv
stage3_8c_boundary_diagnostics.csv
```

## Final Confirmation

```text
stage3_8c_r1_2_final_confirmation_summary.md
stage3_8c_r1_2_final_confirmation_gate.json
```

## Metadata

```text
metadata/input_config.yaml
metadata/run_source_metadata.json
metadata/resolved_search_space_snapshots.json
metadata/material_profile_snapshots.json
metadata/common_validation_grid.csv
```

## Reproducibility

最低限、

- final source/config fingerprint
- git HEAD
- branch
- source snapshotまたはscoped diff
- SHA-256 manifest

を含める。

過剰な履歴保存は不要。

---

# 19. Production結果の解釈

Productionでは2 seedsを使用するため、Pilotより強い比較が可能になる。

ただしProduction完了直後に、

```text
T0を採用
T1をdrop
T2をdrop
```

などをCodex単独で決定してはならない。

結果をreview bundleにまとめて停止する。

Topology promotion / Stage 3.9移行はChatGPTレビュー後に決定する。

---

# 20. Repository保護

引き続き以下は禁止する。

- `git reset --hard`
- unrelated user changesの削除
- repository全体restore
- 無断commit
- 無断push
- historical artifactsの書き換え

ただし今回、完全clean working treeをProduction条件とはしない。

重要なのは**Productionで使用するsource/config fingerprintの固定**である。

---

# 21. 今回の再現性方針

今後Stage 3.8では以下を原則とする。

### 必要

- source/config identity
- deterministic config recording
- seed recording
- major code snapshot/diff
- final outputs
- manifest

### 不要

- artifact byte-for-byte reproduction
- runtime reproduction
- timestamps reproduction
- intermediate report完全再現
- historical bundle完全保存
- minor report-only editsごとのPilot再実行

今回のFinal Confirmationをもって、Stage 3.8 Production前の再現性確認は終了する。

---

# 22. 禁止事項

Final PilotでPASSした後に、理由なく追加Pilotを繰り返さない。

また以下は禁止。

- initializer再設計
- search bounds縮小
- geometry constraint変更
- objective変更
- COM変更
- topology変更
- L-SHADE変更
- specification変更
- GPT-6 Sol追加レビューによる不要な停止
- Monte Carlo再検証
- R1/R1.1/R1.2詳細比較の再作成
- Production fingerprint gateの無効化
- Production完了後のStage 3.9自動開始

---

# 23. 実行フロー

```text
Current final source/config freeze
        ↓
fingerprint記録
        ↓
R1.2 Final Pilot
256 × 6 cells
        ↓
PASS?
   ├─ NO
   │   ↓
   │ FAIL_STOP
   │
   └─ YES
       ↓
Final Confirmation marker保存
       ↓
同一fingerprint確認
       ↓
Stage 3.8C Production
8k × 2 seeds × 6 cells
       ↓
Production review bundle生成
       ↓
STOP
       ↓
ChatGPT review
```

---

# 24. Final Pilot終了時の報告

PASS時：

```text
Stage 3.8C-R1.2 Final Confirmation: PASS

Fingerprint:
MATCH

Pilot cells:
6 / 6 PASS

Initial population:
6 / 6 geometry-valid

Physics:
6 / 6 valid

Fixed-design sanity:
6 / 6 PASS

Tests:
PASS

Production:
STARTING with identical source/config fingerprint
```

FAIL時：

```text
Stage 3.8C-R1.2 Final Confirmation: FAIL_STOP

Failure reason:
<reason>

Production:
NOT STARTED
```

---

# 25. Production完了時の報告

Production終了後は以下だけを報告する。

```text
Stage 3.8C Production:
COMPLETED / FAILED

Evaluations:
<completed> / 96000

Cells completed:
x / 6

Seeds completed:
x / 12 runs

Physics failures:
<count>

Source/config fingerprint:
<fingerprint>

Review bundle:
<path>

Stage 3.9:
NOT STARTED
```

その後停止すること。