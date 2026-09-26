# Historical Cleanup Pre-Deletion Correction 作業指示書

> **歴史的な引き継ぎ・作業指示の記録です。現行手順ではありません。** 本文中のブランチ名、コミット SHA、パス、件数、コマンド、停止条件は作成当時の状態を示します。実行前に現行状態と当該タスクの承認を確認してください。現在の開発方針は[ロードマップ](../project_roadmap.md)、[現行ベースライン](../history/current_baseline.md)、[アーキテクチャ概要](../architecture_overview.md)、C2C の運用・セキュリティ方針は[C2C documentation](../c2c/README.md)を参照してください。

## 1. 目的

対象ブランチ:

`codex-historical-cleanup`

現在のHEAD:

`baed01c365a5a7d0f87ae03344475037d9e476b8`

cleanup開始時のmain:

`444d3a430797d32d688f74bb76ffda615cddfba0`

現在までに、

- historical knowledgeの集約
- `ReleasedFilterDesign` / released DMS simulationの抽出
- DMS study共通helperの抽出
- L-SHADE record serializationの抽出
- Stage 3.8CからStage 3.8 runnerへの直接依存除去
- historical handoff/reportへのruntime依存削減

が実施されている。

方向性は妥当であり、この作業では大規模なhistorical file削除へ進む前に、レビューで見つかった残存課題を修正し、dependency extractionを安全にcloseする。

この作業では**過去Stageコードの大量削除はまだ行わない**。

---

# 2. 最重要方針

今回守るべきものは、

**過去コードの再実行互換性ではなく、実験結果・判断・科学的根拠・参照可能な履歴**

である。

一方で、現在および今後使用するコードについては、

- historical Stage module
- historical report
- handoff document
- ignored `runs/` ディレクトリ

への不必要なruntime dependencyを残さない。

---

# 3. 禁止事項

以下は行わない。

- COM equation変更
- network calculation変更
- objective変更
- comparator semantics変更
- L-SHADE algorithm変更
- RNG order変更
- bounds変更
- geometry constraints変更
- budget変更
- checkpoint semantics変更
- Stage 3.8C Production再実行
- 過去Stage optimizer再実行
- `runs/` 内のcanonical numerical result書き換え
- Git history rewrite
- force push
- historical Stage modulesの大量削除
- historical tests/configsの大量削除

今回の作業はarchitecture correctionとverificationのみとする。

---

# 4. Task A — Freeze tagをremoteへ確実に保存

現在、

`reports/historical_cleanup_freeze_20260925.md`

には、

`archive/pre-historical-cleanup-2026-09-25`

というfreeze tagが存在すると記録されている。

しかしGitHub remote上ではtagを確認できなかった。

## 実施内容

cleanup開始commit

`444d3a430797d32d688f74bb76ffda615cddfba0`

を指すannotated tag

`archive/pre-historical-cleanup-2026-09-25`

がローカルに存在するか確認する。

### 既に正しいtagが存在する場合

そのtagをremoteへpushする。

### 存在しない場合

上記commitを指すannotated tagを作成し、remoteへpushする。

tag message例:

`Freeze repository before historical cleanup`

## 必須確認

remote上のtagが、

`444d3a430797d32d688f74bb76ffda615cddfba0`

を最終的に参照していることを確認する。

tagがannotated tag objectを経由する場合は、peeled commitまで確認する。

## 禁止

- 別commitへtagを付けない
- cleanup後commitへtagを付けない
- 既存の正しいtagを不用意に付け替えない

---

# 5. Task B — branch名記録の修正

現在のremote branchは、

`codex-historical-cleanup`

である。

一部reportでは、

`codex/historical-cleanup`

と記録されている。

## 修正対象

少なくとも以下を確認する。

- `reports/historical_cleanup_freeze_20260925.md`
- `reports/historical_cleanup_architecture_escalation.md`
- `reports/escalation_log.md`

branch名を記録する箇所は、

`codex-historical-cleanup`

へ統一する。

## 注意

これはprovenance documentation correctionであり、数値実験結果には影響しない。

---

# 6. Task C — `lshade_records.py` のhistorical dependency解消

現在、

`src/sawopt/studies/lshade_records.py`

は、

`src/sawopt/studies/convergence_evidence.py`

の

`apply_checkpoint_evidence`

へ依存している。

`lshade_records.py` 自体はcurrent reusable infrastructureとして抽出されたが、その下にhistorical study module dependencyが残っている。

これを解消する。

---

## 6.1 `convergence_evidence.py` の役割判定

現在の `convergence_evidence.py` は、

- checkpoint telemetry
- frequency-grid events
- recovery events
- boundary events
- best-so-far trace

から、

- `grid_converged`
- `recovery_pending_confirmation`
- `boundary_pending_confirmation`
- `hard_bound_unresolved`
- `micro_polish_improvement`
- `fraction_of_budget_at_last_significant_improvement`

を導出するoptimizer-independent utilityである。

これはStage 3.x専用protocolというより、checkpoint/convergence telemetry処理として再利用可能である。

したがって削除対象にせず、canonical ownershipへ移す。

---

## 6.2 推奨配置

第一候補:

`src/sawopt/optimization/convergence_evidence.py`

理由:

- optimizer本体ではなくoptimizer-independent evidence derivation
- search/accounting/countersと近い責務
- `studies/` からhistorical意味を外せる

他により自然な既存moduleが明確に存在する場合のみ変更してよい。

新しい細分化moduleを大量に作らないこと。

---

## 6.3 移動対象

原則として現在の以下をsemantics変更なしで移す。

- `EVIDENCE_FIELDS`
- `_number`
- `_trace_primary`
- `_last_significant_fraction`
- `_event_at_checkpoint`
- `_event_bool`
- `derive_checkpoint_evidence`
- `apply_checkpoint_evidence`

必要ならprivate helper構成は整理してよいが、output semanticsを変えない。

---

## 6.4 caller更新

少なくとも、

`src/sawopt/studies/lshade_records.py`

をcanonical moduleへ向ける。

その他repository内のcurrent callerも検索し、適切に更新する。

historical study moduleが一時的に旧import pathを必要とする場合は、

`studies/convergence_evidence.py`

を短期compatibility re-exportにしてもよい。

ただしこれは**次のhistorical deletion phaseで削除可能なtemporary shim**として明記する。

可能なら今回の時点でinternal callerをすべてcanonical importへ移す。

---

# 7. Task D — Final Confirmation gateの配置方針修正

現在、

以下の2 config:

- `configs/studies/stage3_8c_r1_2_final_confirmation.yaml`
- `configs/studies/stage3_8c_r1_2_production.yaml`

の

`final_confirmation_test_gate`

が、

旧:

`reports/stage3_8c_r1_2_final_confirmation_test_gate.json`

から、

新:

`runs/stage3_8c_r1_2_final_confirmation_20260924/metadata/final_confirmation_test_gate.json`

へ変更されている。

この変更は再検討する。

---

## 7.1 問題

`runs/` は、

- GitHubのcurrent source treeに含まれない
- external/ignored experimental dataとして扱う領域
- active source configの必須dependencyにするとrepository単体で意味が完結しない

ため、historical report依存除去の代替先としては適切ではない。

---

## 7.2 今回の方針

過去Stage 3.8C production configを長期的に再実行互換維持する必要はない。

したがって、

**historical configを存続させるためだけにgate fileをrunsへ移植しない。**

原則として今回の変更はrevertする。

つまり、

`final_confirmation_test_gate`

は一旦元の

`reports/stage3_8c_r1_2_final_confirmation_test_gate.json`

参照へ戻す。

そのうえで次のhistorical deletion phaseで、

- config
- historical gate
- historical Stage 3.8C compatibility execution path

をまとめて削除する。

---

## 7.3 例外

もし調査の結果、

`stage3_8c_r1_2_production.yaml`

またはfinal-confirmation configが今後のcurrent production/reference studyとして継続利用されることが明確である場合のみ、

小さなcanonical immutable inputとして、

例:

`configs/reference/`

または同等のcurrent source-controlled locationへ配置する案を採用してよい。

この場合も、

`runs/`

をactive config dependencyにはしない。

判断理由をreportへ記録する。

---

# 8. Task E — Historical knowledge文書の証拠レベル補強

現在、

- `docs/history/experiment_register.md`
- `docs/history/current_baseline.md`

は概ね良好であり、大きく書き換える必要はない。

ただしStage 3.1〜3.5など、canonical raw runが現在のcheckoutに存在しない項目について、証拠レベルをもう少し明確にする。

---

## 8.1 目的

将来、

「この数字はcanonical raw artifactから直接確認されたのか」

それとも、

「当時のreport/config/decision summaryに記録された値なのか」

を識別できるようにする。

---

## 8.2 実装方針

各experiment sectionに大きなmetadata blockを追加する必要はない。

簡潔に例えば、

`Evidence level: canonical run`

`Evidence level: retained report/config`

`Evidence level: historical decision record only`

のような表記を追加する。

少なくとも以下を分類する。

### Prototype

retained result documentベース。

### 50 Ω hybrid

retained result documentベース。

### Stage 3.1–3.4b

retained config / README / project decision recordベース。
raw canonical runなし。

### Stage 3.3–3.5

retained config / README / escalation historyベース。
raw canonical runなし。

### Stage 3.6

canonical run / review bundle / recorded commitあり。

### Stage 3.7

canonical run / config / escalation evidenceあり。

### Stage 3.8C

canonical production run / review bundle / closeout evidenceあり。

---

## 8.3 注意

既存数値を新しく推測しない。

証拠がないcommit SHA、run SHA、metricを補完しない。

不明なものは不明のままとする。

---

# 9. Task F — current dependency audit

大量削除前に、current codeがhistorical Stage modulesへ依存していないことを静的に調査する。

最低限以下を対象にする。

`src/sawopt/`

---

## 9.1 検索対象

以下へのimportを検索する。

- `stage3_6_*`
- `stage3_7_*`
- `stage3_8_dual_material_dms_topology_fast_screen`
- `optimizer_ab`
- `convergence`
- `continuation`
- `search_efficiency`
- `phase_c_*`
- `matched_protocol_parity`
- `preproduction`

---

## 9.2 分類

各参照を、

### Current dependency

今後のcurrent implementationが必要としている。

→ canonical moduleへ移す。

### Historical-only dependency

削除予定historical module同士の依存。

→ 今回は残してよい。

### Compatibility-test dependency

旧import pathの存在確認だけ。

→ next deletion phaseで削除対象。

に分類する。

結果をreportへ記録する。

---

# 10. Task G — characterization tests

今回の移動によりnumerical semanticsが変わっていないことを確認する。

production optimizationは実行しない。

---

## 10.1 Released DMS

以下を確認する。

- `ReleasedFilterDesign` field equality
- `section_geometry()` equality
- T0 decode equality
- `simulate_released_filter()` Y parameter parity
- S parameter parity
- key metrics parity

既存testが十分なら追加しすぎない。

---

## 10.2 DMS topology common

以下を確認する。

- T0/T1/T2 fixed design behavior
- T0 legacy/generalized/released parity
- T1 deterministic/passive/reciprocal
- T2 Y sum identity
- material provider selection
- initial-design decode

---

## 10.3 L-SHADE record

old/new pathについて、

controlled backend fixtureを使用し、

timing値を固定または比較対象から適切に除外した上で、

serialized record semanticsが一致することを確認する。

最低限、

- unique evaluation counts
- population fields
- duplicate/cache accounting
- terminal budget
- checkpoint metadata
- convergence evidence
- frequency-grid metadata

を比較する。

---

## 10.4 convergence evidence

canonical locationへ移動後、

旧実装との代表fixture parityを確認する。

特に、

- grid fixed
- frequency-grid changeあり
- recovery eventあり
- boundary eventあり
- hard-bound eventあり
- incomplete telemetry

をカバーする。

---

# 11. Task H — full regression

すべての修正後にfull test suiteを実行する。

推奨:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
```

またはrepositoryで標準化されたfull test command。

cleanup開始時baseline:

`288 passed`

である。

テスト数は今回多少増減してよいが、

**failure 0**

を必須とする。

---

# 12. GitHub Actions

可能であればbranchをpush後、通常のCIがtriggerされる構成ならCI resultも確認する。

現在 `codex-historical-cleanup` branchではGitHub Actions runが確認されていない。

CIがbranch pushではtriggerされない設定なら、無理にworkflowを変更しない。

その場合はlocal full pytest結果をreview reportへ明記する。

---

# 13. 作業結果report

新規:

`reports/historical_cleanup_pre_deletion_correction.md`

を作成する。

最低限以下を記載する。

## Git state

- branch
- starting HEAD
- ending HEAD
- freeze tag
- freeze tag target commit
- remote tag verification

## Corrections

- branch-name correction
- convergence evidence ownership
- config/gate dependency decision
- historical evidence-level additions

## Dependency audit

current sourceからhistorical moduleへの残存依存一覧。

各項目について、

- keep
- extracted
- historical-only
- delete-next-phase

を示す。

## Tests

- focused test command
- focused result
- full pytest command
- full result

## Numerical impact

明確に、

`NO NUMERICAL EXPERIMENT RERUN`

`NO COM/NETWORK/OBJECTIVE/OPTIMIZER SEMANTICS CHANGE`

と記録する。

## Next phase readiness

以下を判定する。

`READY_FOR_HISTORICAL_DELETION`

または

`NOT_READY_FOR_HISTORICAL_DELETION`

NOT_READYの場合はblockerを列挙する。

---

# 14. 完了条件

以下をすべて満たした場合のみ今回の作業をcloseする。

- [ ] remote freeze tagが確認できる
- [ ] tagがcleanup前commit `444d3a4...` を指している
- [ ] branch名記録が実際のbranchと一致
- [ ] `lshade_records.py` がhistorical `studies/convergence_evidence.py` に直接依存しない
- [ ] convergence evidence utilityがcanonical ownershipへ移動
- [ ] active production/current configが新たにignored `runs/` dependencyを持たない
- [ ] experiment registerのevidence levelが明確
- [ ] current implementationのhistorical module dependency audit完了
- [ ] Released DMS characterization PASS
- [ ] DMS topology characterization PASS
- [ ] L-SHADE record characterization PASS
- [ ] convergence evidence parity PASS
- [ ] full pytest PASS
- [ ] production optimizerを再実行していない
- [ ] canonical saved numerical outputsを書き換えていない
- [ ] correction report作成済み

---

# 15. 今回は削除しないもの

この作業では、まだ以下を一括削除しない。

- `stage3_6_*`
- `stage3_7_*`
- `optimizer_ab.py`
- `convergence.py`
- `continuation.py`
- `search_efficiency.py`
- `phase_c_*`
- historical tests
- historical configs
- historical `experiments/`
- compatibility shims
- handoff documents
- historical reports

これらの削除は、

`READY_FOR_HISTORICAL_DELETION`

判定後の次作業で行う。

---

# 16. 次フェーズへの引き継ぎ

今回の目的は、

**「旧コードを安全に削除できる状態を作る」**

ところまでである。

次フェーズでは、

1. historical runners削除
2. corresponding tests削除
3. historical configs削除
4. experiments descriptors削除
5. compatibility shims削除
6. CLI registry整理
7. handoff/reports pruning
8. README更新
9. 最終file-count / test-count評価

を実施する。

削除フェーズでは、今回作成した

- freeze tag
- `experiment_register.md`
- `current_baseline.md`
- dependency audit

を安全装置として使用する。
