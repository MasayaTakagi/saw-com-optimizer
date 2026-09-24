# Stage 3.8C Production Closeout Correction
## Counter Gate修正・既存96k結果の再判定・Stage 3.8 Closeout

## 1. 目的

Stage 3.8C Productionでは、

```text
8,000 evaluations / cell
× 2 seeds
× 6 cells
= 96,000 evaluations
```

を完走した。

確認済み事項：

- 96,000 / 96,000 evaluations 完了
- 6 / 6 cells 完了
- 12 / 12 seed runs 完了
- physics failure = 0
- Final Confirmation PASS
- source/config fingerprint一致
- fixed-design sanity PASS
- full test suite PASS
- 48 / 48 checkpoint accounting rows PASS

一方、Production gateではcounter accounting CSVの行数を誤って

```text
6 cells × 2 seeds = 12 rows
```

と期待している。

実際には各seed runに、

```text
2k
4k
6k
8k
```

の4 checkpointsが存在するため、

```text
6 cells
× 2 seeds
× 4 checkpoints
= 48 rows
```

が正しい。

そのため現在のProduction `FAILED` は、

**実験結果のfailureではなく、closeout/gate集計ロジックのfalse failure**

である。

今回の作業では96k Productionを再実行しない。

既存結果を保持したまま、

1. counter gate bug修正
2. 既存96k結果からgate再生成
3. terminal status修正
4. historical artifact整理
5. Stage 3.8C Productionを正式close

する。

---

# 2. 最重要方針

## 再実行禁止

以下を再実行してはならない。

```text
96k Production
```

また、

- 追加seed
- 追加8k run
- Final Pilot再実行
- T1/T2延長探索

も今回のcloseout作業では行わない。

今回の作業は**reporting / validation / closeout correctionのみ**とする。

---

# 3. Production結果の有効性

既存Production結果をcanonical resultとして使用する。

以下の96k結果を破棄・上書きしてはならない。

Production計算自体について、

```text
COMPLETED_VALID_RESULTS
```

として扱う。

ただしGate修正完了まではcloseout statusのみpendingとする。

---

# 4. Work A — Counter Accounting Gate修正

## 4.1 現在の問題

現在のgateでは概ね、

```python
expected_rows = 6 * 2
```

相当のロジックになっている。

これを修正する。

---

## 4.2 正しい期待値

Production run structure：

```text
materials = 2
topologies = 3
seeds = 2
checkpoints = 4
```

したがって、

```text
expected_counter_rows
= 2 × 3 × 2 × 4
= 48
```

となる。

ただし固定値`48`を直接hard-codeするのではなく、可能な限りmetadata/configから導出する。

例：

```python
expected_rows = (
    len(materials)
    * len(topologies)
    * len(seeds)
    * len(checkpoint_budgets)
)
```

---

# 5. Counter Gateで確認すべき内容

行数だけでPASSさせてはならない。

全48 rowsについて以下を要求する。

```text
counter_identity_pass == true
physics_partition_pass == true
valid_physics_within_geometry_valid == true
physics_attempt_identity_pass == true
```

また、

```text
checkpoint budgets
=
2000, 4000, 6000, 8000
```

が各12 seed-runsについて揃っていることを確認する。

つまり、

```text
12 runs × 4 checkpoints
```

が完全に存在すること。

---

# 6. 欠損checkpoint検出

次のケースはFAILにする。

- seed-runが12未満
- checkpointが4未満
- 2k/4k/6k/8kのいずれか欠損
- duplicate checkpoint
- accounting invariant failure
- final 8k row欠損

単純な48行数一致だけではPASSさせない。

---

# 7. Counter Gate unit test

最低限以下を追加する。

## A. 正常48 rows

```text
12 runs × 4 checkpoints
```

でPASS。

## B. 旧誤判定防止

正常48 rowsを、

```text
expected == 12
```

としてFAILさせる旧ロジックが存在しないこと。

## C. checkpoint欠損

47 rows等の場合FAIL。

## D. duplicate checkpoint

行数48でも同じrun/checkpoint重複があればFAIL。

## E. invariant failure

1 rowでもcounter invariantがfalseならFAIL。

---

# 8. Work B — Existing Production Gate再生成

counter gate修正後、

**既存96k artifactだけを使用して**

Production gateを再評価する。

optimizerやphysics計算は実行しない。

期待結果：

```text
Stage 3.8C Production:
COMPLETED
```

または既存schemaに対応するterminal success state。

---

# 9. Gate再評価項目

Production closeout gateでは少なくとも以下を確認する。

```text
evaluations = 96000 / 96000
cells = 6 / 6
seed runs = 12 / 12
physics failures = 0
counter accounting = PASS
source/config fingerprint = MATCH
finite production metrics = PASS
common-grid validation = PASS
```

すべて満たした場合のみterminal PASSとする。

---

# 10. Work C — status.json修正

現在、

```text
state = RUNNING
```

等の非terminal stateが残っている場合は修正する。

Production完了済みなので、既存schemaに合わせて、

```text
COMPLETED
```

または正式なsuccess terminal stateへ変更する。

statusには最低限、

```text
evaluations_completed = 96000
evaluations_expected = 96000
cells_completed = 6
seed_runs_completed = 12
physics_failures = 0
counter_accounting = PASS
```

を反映する。

---

# 11. Source of Truth

既存の96k result filesをcanonicalとする。

Closeout correctionで、

- objective値
- max violation
- design parameters
- checkpoints
- seed result
- physics result

を書き換えてはならない。

今回変更可能なのは主に、

- gate logic
- gate output
- status
- summary
- closeout report
- test
- bundle metadata

である。

---

# 12. Work D — Production Summary修正

Production summaryでは現在のfalse `FAILED` 表記を修正する。

ただし履歴を隠さない。

例えば、

```text
Initial closeout status:
FAILED due to counter-row expectation bug

Corrected closeout status:
COMPLETED

96k optimizer/physics rerun:
NOT PERFORMED
```

と記載する。

---

# 13. Historical Artifactの扱い

review bundle内に、

```text
production not run
```

等の旧R1/R1.2文書が存在する場合、削除・改変しなくてよい。

ただしcanonical Production summaryから見て誤解されないよう、

```text
HISTORICAL / PRE-PRODUCTION ARTIFACT
```

であることを明示する。

historical recordsを書き換えてはならない。

---

# 14. Performance結果は変更しない

今回のcloseout correctionではtopology性能結果を再計算しない。

既存Production結果をそのまま使用する。

参考となるcommon-grid max violation median：

```text
M0:
T0 ≈ 0.504
T1 ≈ 0.654
T2 ≈ 0.675

MLIT:
T0 ≈ 0.782
T1 ≈ 0.492
T2 ≈ 0.706
```

ただしsummaryでは、

**全候補filter-feasible未達**

であることを維持する。

---

# 15. Topology解釈

Stage 3.8 closeoutでは、結果の意味を以下程度に留める。

## M0

今回の探索条件ではT0が最小violation。

ただし、

- hypothetical material profile
- boundary activityあり
- T1/T2は継続改善あり

のため、絶対的なtopology superiorityとは結論しない。

---

## MLIT

今回の8k × 2 seed条件では、

```text
T1
```

が最小violation。

したがって今後のMLIT DMS候補として、

```text
Primary candidate: T1
```

と整理してよい。

ただしT2は8k時点でも改善傾向が大きいため、

```text
Secondary / unresolved candidate: T2
```

として保持する。

T2をdropしてはならない。

---

# 16. Material横断比較

以下のsearch-space differenceを再度明記する。

```text
M0:
aperture = 30–150 µm

MLIT:
aperture = 30–180 µm
```

またM0 / MLITのCOM provenanceも異なる。

したがって、

```text
MLIT/T1 > M0/T0
```

のような直接的な材料優劣判定は行わない。

---

# 17. Stage 3.8 Closeoutの位置づけ

Stage 3.8は、

**DMS topology fast screening**

としてcloseする。

結論は、

```text
Stage 3.8 successfully identified topology trends,
but did not produce a fully filter-feasible final B28 design.
```

相当とする。

つまり、

- Production execution成功
- topology傾向取得成功
- final design完成ではない

という位置づけ。

---

# 18. Stage 3.9について

今回の作業ではStage 3.9を開始しない。

Closeout完了後停止する。

次工程についてはChatGPTレビュー後に決定する。

特に、

- MLIT T1/T2延長探索
- hybrid topology導入
- ladder追加
- impedance sweep

を自動開始してはならない。

---

# 19. Tests

修正後、最低限以下を実施する。

1. new counter-gate tests
2. Production gate regression
3. existing Stage 3.8 tests
4. full repository test suite

COM/optimizerを96k再実行する必要はない。

---

# 20. GPT-6 Sol

今回のcloseout correctionについて、新しいGPT-6 Solレビューは必須ではない。

既存routing設定：

```text
gpt6sol
```

を維持する。

旧`gpt5.6sol`へ戻してはならない。

routing regression testも既存suiteで維持する。

---

# 21. Repository保護

引き続き以下は禁止。

- `git reset --hard`
- unrelated user changes削除
- repository全体restore
- 無断stash
- 無断commit
- 無断push

pre-existing dirty stateを保持する。

今回の変更だけscoped diffとして記録する。

---

# 22. Corrected Review Bundle

新しいbundleを作成する。

推奨：

```text
stage3_8c_production_closeout_corrected_review.zip
```

---

# 23. Bundle必須内容

## Canonical summary

```text
REVIEW_ME.md
stage3_8c_production_closeout_summary.md
stage3_8c_production_gate_corrected.json
test_summary.md
```

## Existing production results

既存96k Production resultsをそのまま含める。

```text
stage3_8c_production_results.csv
stage3_8c_all_seed_results.csv
stage3_8c_seed_comparison.csv
stage3_8c_counter_accounting.csv
stage3_8c_validated_responses.csv
stage3_8c_boundary_diagnostics.csv
```

## Closeout correction

```text
counter_gate_correction_report.md
stage3_8c_production_closeout_status.json
```

## Metadata

既存metadataを保持する。

## Reproducibility

最低限、

- production source/config fingerprint
- git HEAD
- branch
- scoped closeout diff
- SHA-256 manifest

を含める。

---

# 24. REVIEW_ME.md

冒頭で明示する。

```text
Stage 3.8C Production:
COMPLETED

96k rerun:
NOT PERFORMED

Original FAILED reason:
counter accounting row-count gate bug

Corrected counter accounting:
48 / 48 checkpoint rows PASS

Stage 3.8:
READY FOR CLOSEOUT REVIEW

Stage 3.9:
NOT STARTED
```

---

# 25. Production Gate期待結果

修正後は概ね以下となること。

```text
evaluations:
96000 / 96000

cells:
6 / 6

seed runs:
12 / 12

checkpoints:
48 / 48

counter accounting:
PASS

physics failures:
0

fingerprint:
MATCH

production state:
COMPLETED
```

---

# 26. Manifest

corrected review bundleについてSHA-256 manifestを再生成し、

全file consistencyを検証する。

ただし96k raw resultを再生成しない。

---

# 27. 禁止事項

今回特に禁止する。

- 96k Production rerun
- optimizer再実行
- physics result再計算
- seed追加
- budget追加
- search-space変更
- objective変更
- COM変更
- T2削除
- topology定義変更
- Stage 3.9開始
- hybrid design開始
- impedance sweep開始
- historical result書き換え
- fingerprint gate無効化

---

# 28. 完了条件

以下すべてで完了。

## Gate correction

- expected checkpoint accounting row数が正しく導出される
- 48/48 rows検証PASS
- 欠損/duplicate/invariant-failure test PASS

## Production closeout

- 96k resultを再利用
- evaluations 96000/96000
- cells 6/6
- seed runs 12/12
- physics failure 0
- source/config fingerprint MATCH
- Production state COMPLETED

## Tests

- new gate tests PASS
- Stage 3.8 regression PASS
- full suite PASS

## Documentation

- original false failureを記録
- corrected statusを記録
- 96k rerun無しを明記
- historical artifactsを明確に区別

## Stop

- corrected review bundle生成
- Stage 3.9 NOT STARTED
- review待ちで停止

---

# 29. 作業終了時の報告形式

```text
Stage 3.8C Production Closeout Correction:
COMPLETED / FAILED

96k Production rerun:
NO

Evaluations:
96000 / 96000

Cells:
6 / 6

Seed runs:
12 / 12

Counter checkpoints:
48 / 48 PASS

Physics failures:
0

Fingerprint:
MATCH / MISMATCH

Tests:
PASS / FAIL

Production final state:
COMPLETED / FAILED

Stage 3.9:
NOT STARTED

Corrected review bundle:
<path>
```

その後停止すること。