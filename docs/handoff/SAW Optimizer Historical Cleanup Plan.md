# SAW Optimizer Historical Cleanup Plan

> **歴史的な引き継ぎ・作業指示の記録です。現行手順ではありません。** 本文中のブランチ名、コミット SHA、パス、件数、コマンド、停止条件は作成当時の状態を示します。実行前に現行状態と当該タスクの承認を確認してください。現在の開発方針は[ロードマップ](../project_roadmap.md)、[現行ベースライン](../history/current_baseline.md)、[アーキテクチャ概要](../architecture_overview.md)、C2C の運用・セキュリティ方針は[C2C documentation](../c2c/README.md)を参照してください。

## 1. 目的

現在の `saw-com-optimizer` はStageの進行に伴い、

- 過去Stage専用の実験スクリプト
- 過去Stage専用のテスト
- 過去実験のconfig
- compatibility shim
- Codex作業指示書
- 一時的なレビュー・監査レポート

が累積している。

今後は、過去実験の再実行互換性を維持することを目的としない。

代わりに、以下を確実に保存する。

1. 何を検証したか
2. どの条件で検証したか
3. どのような結果が得られたか
4. その結果から何を判断したか
5. どの判断が後続Stageへ引き継がれたか
6. 判断上の制約・未解決事項
7. 必要になった場合に元コード・元データへ戻れる参照先

最終目標は、

> 現在と今後のSAW設計検討に必要なコードだけを通常のworking treeに残し、過去Stageについては「知識」と「参照可能な履歴」だけを残す。

こととする。

---

# 2. 保存ポリシー

過去資産を4クラスに分類する。

## A. Living implementation

今後も変更・テスト・利用する実装。

例:

- COM計算
- network計算
- metrics
- current material model
- DMS topology
- optimizer backend
- checkpoint/provenance
- 現在使用中のDMS topology study
- 将来使用するhybrid関連の共通実装

これらは通常の `src/` / `tests/` に残す。

---

## B. Historical knowledge

コードは不要だが、将来の判断に必要な情報。

これについては少数の文書へ集約する。

新規作成する中心文書は原則2つだけとする。

### `docs/history/experiment_register.md`

各主要実験について以下を記録する。

- Stage / Experiment ID
- 検証目的
- 主要な実験条件
- 使用モデル・material
- optimizer / budget / seedなど重要条件
- 主要な定量結果
- 結論
- 当時の判断理由
- 後続Stageへ引き継いだ内容
- 後に否定・修正された内容
- 未解決事項
- canonical run / review bundle
- Git commit
- 必要なら元config名

単なる時系列ログにはしない。

「その結果から何を学んだか」を主情報とする。

### `docs/history/current_baseline.md`

過去実験を経て現在採用している前提だけをまとめる。

例:

- 現在採用しているCOMモデル
- literature COMの扱いと限界
- DMS topology T0/T1/T2の定義
- geometry constraint
- aperture範囲
- optimizer
- comparator
- initializer
- checkpoint policy
- 50 Ω DMS検討で確定した事項
- impedance sweepへ引き継ぐ事項
- hybrid検討へ引き継ぐ事項
- 現時点で未解決の問題

今後のCodex/ChatGPTは、まずこの文書を読めばプロジェクトの現在位置が分かる状態を目標とする。

---

## C. Historical implementation

過去StageのPython、test、config、作業指示書など。

これらは現在のworking treeから削除する。

ただし削除前にGitの固定点を作る。

例:

`archive/pre-historical-cleanup-stage3.8c`

のようなannotated tagをcleanup直前のmainに作る。

これにより、

「Stage 3.6 Gate 2B-Bのコードを確認したい」

となった場合でも、通常のmainへ復元する必要はなく、

`git show <tag>:<path>`

または一時checkoutで参照できる。

**過去コードを今後のCIで動作保証する必要はない。**

---

## D. Raw experimental artifacts

`runs/`、review bundle、CSV、JSON、NPZ等。

今回のcleanupでは削除しない。

ソースコード整理と実験データ整理を分離する。

少なくともexperiment registerには、

- canonical run名
- review bundle名
- 重要CSV/JSON
- 保存場所
- 可能ならSHA-256

を記録する。

将来的に外部ストレージへ移動しても、experiment registerから所在を追跡できるようにする。

---

# 3. Cleanup前の知識保存

削除作業より先に実施する。

## Stage 1 / prototype

保存する事項:

- 初期COMモデル
- impedance sweepの意味
- 45 Ω付近が暫定上位だったこと
- ただし仮COMモデル上の結果に限定されること
- matchingだけではloss問題を解決できない可能性
- calibration/FEMが必要という判断

既存の

- `docs/results/prototype_results_ja.md`
- `docs/reviews/review_ja.md`

からexperiment registerへ必要情報を統合する。

統合確認後、元文書は削除可能。

---

## Hybrid 50 Ω

保存する事項:

- DMS単体よりladder追加が改善したこと
- 当時の上位構成
- insertion loss等の代表値
- それでも仕様未達だったこと
- 832–862 MHz attenuationとpassband lossが主要課題だったこと
- 将来的にhybrid topologyを再検討する根拠

`docs/results/hybrid_50ohm_results_ja.md` の重要結果をexperiment registerへ統合する。

---

## Stage 3.1–3.4b

保存する事項:

- convergence評価方法がどう変化したか
- unique evaluation budgetを採用した理由
- Stage 3.4bで256kまで確認した結果
- 64kでは十分と断定できなかったこと
- search-space設計とoptimizer効率が次の主要課題になったこと
- center_outer_same等について得られた結論

個々のrunnerを保存する必要はない。

---

## Stage 3.5

特に重要。

保存する事項:

- Legacy-DE vs L-SHADE比較
- 初期にはLegacy-DE優位に見えた理由
- matched protocolで比較条件を揃えた結果
- search-space縮小戦略
- Phase C追加確認
- Phase Dを実施しなかった理由
- 今後L-SHADEを使用する根拠
- frozen S1が何を表していたか

現在version管理されている

`artifacts/stage3_5/phase_a_revised/search_space_s1.yaml`

についても、その意味をexperiment registerに記録する。

現在の実装から依存がなくなれば、ファイルそのものは削除可能。

---

## Stage 3.6

保存する事項:

- 50 Ω状態でのDOF release
- Gate 2Aの意味
- G1/G2等で何を解放したか
- asymmetric port impedanceを検討した理由
- Gate 2B-A/B
- Gate 2C
- 左右非対称DMSなので両port独立探索が必要と判断した経緯
- 50 Ω referenceとして後続Stageへ何を引き継いだか

現在Stage 3.8が使用している

`ReleasedFilterDesign`

等は歴史情報ではなく再利用可能な設計表現なので、Stage 3.6 moduleから切り離して `problem/` へ移す。

---

## Stage 3.7

保存優先度は非常に高い。

保存する事項:

- literature COMを探した理由
- source completenessの問題
- COM parameterを他source/M0から補完しない方針
- normalized COM reconstruction
- source-device reconstructionの限界
- 42°YX-LiTaO3 profileの出典
- evaluation-onlyであること
- FEM/measurementなしではproduction-qualified claimができないこと
- MLIT profileの現在の位置づけ
- aperture検討
- Stage 3.8へ引き継いだmaterial assumptions

現在使われている

`configs/models/stage3_7b_r1_normalized_literature_profile.yaml`

はStage番号付きでも**現役のmaterial input**なので削除しない。

後で必要なら名称だけrole-based nameへ変更する。

---

## Stage 3.8 / 3.8C

現在へ直結するため最も詳細に残す。

最低限以下を保存する。

- T0/T1/T2 topologyの定義
- T0 parity validation
- T1の5-IDT signed port mapping
- T2 parallel Y-matrix formulation
- Stage 3.8初回rankingがgeometry ranking問題で無効化されたこと
- geometry-first comparator導入理由
- R1でT2 initializer rejectionが90%超となったこと
- R1.1 conditional initializerを試した理由
- distribution bias懸念
- R1.2 independent-uniform + rejectionへ戻した理由
- R1.2 pilot PASS
- Final Confirmation
- Productionの結果
- production closeout時のcounter row-count bug
- 96kを再実行せず既存canonical resultを再監査したこと
- Stage 3.8の最終的なtopology interpretation
- filter-feasible designには到達していないこと
- Stage 3.9開始前の残課題

この情報を `current_baseline.md` にも要約する。

---

# 4. 共通実装抽出

歴史コード削除前に、現在のStage 3.8依存を解消する。

## 4.1 Stage 3.6から抽出

現在、

`stage3_8_dual_material_dms_topology_fast_screen.py`

が

`stage3_6_gate2a.py`

から以下のような機能を利用している。

- ReleasedFilterDesign
- release schema
- decoder
- released filter simulation

これらをStage番号付きmoduleから外す。

候補:

`src/sawopt/problem/released_dms.py`

あるいは既存の

`src/sawopt/problem/dms_topologies.py`

へ統合する。

ファイル数増加を避けられるなら後者を優先する。

Stage 3.6特有の

- Gate
- stop marker
- review bundle
- old run handling
- plotting
- Stage metadata

は移植しない。

---

## 4.2 optimizer_abから抽出

Stage 3.8が必要としている `lshade_record` 等の共通部分だけを、

既存の

- `optimizers/`
- `optimization/`

の適切なmoduleへ移す。

`optimizer_ab.py` 全体を残さない。

---

## 4.3 Stage 3.8 module間依存

現在、

`stage3_8c_r1_geometry_gate.py`
→
`stage3_8_dual_material_dms_topology_fast_screen.py`

という歴史Stage間依存がある。

共通の

- topology
- decoder
- provider selection
- evaluation

をcanonical layerへ移した後、

現行studyをrole-based nameへ移行する。

候補:

`src/sawopt/studies/dms_topology_screening.py`

R1/R1.1/R1.2という過去revisionの互換経路は、現在のproduction semanticsに不要なら削除する。

---

# 5. 過去実験コード削除

共通依存を解消した後に行う。

主な削除候補:

- `continuation.py`
- `convergence.py`
- `convergence_evidence.py`
- `optimizer_ab.py`
- `search_efficiency.py`
- `phase_c_supplement.py`
- `phase_c_final_confirmation.py`
- `matched_protocol_parity.py`
- `preproduction.py`
- `stage3_6_*`
- `stage3_7_*`

ただし現在のmaterial/profile/topologyに必要な部分が残っていないことを静的import検査で確認してから削除する。

---

# 6. 過去テスト削除

原則:

> 削除した過去Stage implementationの挙動を保証するtestも一緒に削除する。

対象候補は現在確認できているだけでも約16ファイル。

例えば、

- `test_stage3.py`
- `test_stage32.py`
- `test_stage33.py`
- `test_stage331.py`
- `test_stage34b_convergence.py`
- `test_search_efficiency.py`
- `test_phase_c_*`
- `test_stage3_6_*`
- `test_stage3_7b_r2_features.py`

等。

ただしテストが検証していた**一般原理**まで失ってはいけない。

例えば、

- deterministic RNG
- integer canonicalization
- comparator ordering
- convergence budget accounting
- checkpoint accounting
- topology parity
- passivity / reciprocity
- COM physics regression

のような一般性のあるテストは、current canonical moduleのテストへ移して残す。

つまり、

**Stageのテストは消す。原理のテストは残す。**

---

# 7. Config整理

過去Stageを再実行しないため、

Stage 2〜3.7のexperiment-specific configは原則削除可能。

残すのは、

- current baseline
- current COM/material profile
- current DMS topology study
- 今後使用するhybrid
- 将来のimpedance study

のみとする。

Stage 3.2〜3.4 fragment configも、依存がなくなれば削除する。

---

# 8. `experiments/`整理

現在の `experiments/` は過去Stageのdescriptorが多数存在する。

過去実験を再実行しないなら、これらを残す意味は小さい。

過去experiment descriptorは削除し、

`experiments/`

を今後の「active experimentだけ」の領域に変更する。

新しい実験が終了したら、

1. experiment registerへ結果を記録
2. 判断をcurrent baselineへ反映
3. experiment-specific implementation/config/testを削除できるか判定

というライフサイクルにする。

---

# 9. Compatibility shim削除

現在 `src/sawopt/optimization/` に約10個存在する旧module compatibility shimも整理する。

過去CLIを維持する要件がないため、

- `stage2_study.py`
- `stage32_study.py`
- `stage33_study.py`
- `stage331_preprod.py`
- `convergence_study.py`
- `hybrid_study.py`
- 旧optimizer import shim

等は、現行コードから参照されていないことを確認後に削除する。

`__main__.py` のregistryも同時に整理する。

過去 `study.type` aliasも削除する。

---

# 10. 作業指示書・reports整理

## docs/handoff

完了済み作業指示書は、experiment registerへ重要判断を転記後、原則削除する。

Git tagから全文を参照できるため、mainに保持しない。

## reports

一時的な、

- pre-work Git state
- test summary
- pilot report
- escalation packet
- routing test
- baseline snapshot

なども同様。

ただし現在のコードがこれらを実行時dependencyとしてSHA/hash参照している箇所がある。

これは先に除去する。

**future production codeは過去のhandoff/reportファイルに依存してはならない。**

必要なprovenanceはrun metadataへ保存する。

---

# 11. async / Codex callback系

これは第一回cleanupでは全面削除しない。

ただし別cleanup候補とする。

現在、

- `.codex/hooks`
- `codex_callback.py`
- orchestration関連実装
- orchestration tests

がまとまったサブシステムになっている。

Codex session自動再開機能は以前凍結したため、今後必要なのが単純なdetached optimizer executionだけなら、

- detached launch
- status
- process management

だけを残し、

- Codex callback
- session capture hook
- callback専用test

を削除できる可能性がある。

これはhistorical Stage cleanup完了後に別判断する。

---

# 12. Cleanupの実行順序

## Phase A — Freeze

cleanup直前のmainをannotated tagで固定。

さらに、

- HEAD
- current test result
- file inventory
- active dependencies

を記録。

この段階では削除しない。

---

## Phase B — Knowledge consolidation

`experiment_register.md`
と
`current_baseline.md`

を作成。

Stage 1〜3.8Cまでの重要結果・判断を既存docs/reportsから転記。

レビュー時には、

「重要な判断が旧ファイルにしか存在していない」

項目がゼロであることを確認する。

---

## Phase C — Dependency extraction

Stage 3.6 / 3.3等から現在使われている共通実装だけをcanonical moduleへ移す。

数値結果が変わらないことをcharacterization testで確認する。

この段階ではまだ旧moduleを残してよい。

---

## Phase D — Historical implementation removal

旧Stage Python、configs、experiment descriptors、compatibility shimsを削除。

`__main__.py` registryもactive protocolだけにする。

---

## Phase E — Test pruning

削除されたStage implementationのtestを削除。

一般的なphysics / optimizer / topology / lifecycle testだけ残す。

---

## Phase F — Documentation pruning

完了済みhandoff、temporary report、old refactor plan、one-shot maintenance scriptを削除。

READMEを「現在の使い方」だけに書き換える。

---

## Phase G — Verification

最後に以下を確認。

1. full pytest PASS
2. current Stage 3.8 topology regression PASS
3. current material profile load PASS
4. DMS topology parity PASS
5. L-SHADE deterministic smoke PASS
6. checkpoint lifecycle PASS
7. review bundle PASS
8. architecture boundary test PASS
9. historical Stage moduleへのimportが0
10. deleted configへの参照が0
11. deleted report/handoffへのruntime参照が0
12. `experiment_register.md` から全主要Stageの結果を追跡可能
13. `current_baseline.md` だけで次の検討を開始可能

---

# 13. 削除判断のルール

今後も同じ問題を再発させないため、次のルールを採用する。

### 残す

「これから変更して使うもの」

### historyへ要約して削除

「結果や判断は重要だが、コードそのものは不要なもの」

### Git履歴だけに残す

「検証過程としては意味があるが、現在の判断には直接不要なもの」

### repository外へ保存

「生のrun / checkpoint / 大容量artifact」

---

# 14. 目標状態

現在:

- 約303 files
- Python source 約95
- tests関連 約58

第一回historical cleanup後の目標は厳密な数ではなく、おおよそ、

- total files: 180〜210
- Python source: 60〜70
- tests: 35〜40前後

を目安とする。

ただし「ファイル数を減らすための巨大module化」は行わない。

判断基準は、

> 今後このファイルが変更されたとき、プロジェクトとしてその挙動を維持する責任を負いたいか？

とする。

答えがNoであり、実験知識がexperiment registerへ保存済みなら、mainから削除する。

---

# 15. このcleanupで最も重要な非目標

以下は行わない。

- 過去Stageを最新環境で再実行可能にする
- 過去CLIとの互換性を保つ
- 過去config schemaを維持する
- 過去testをPASSさせ続ける
- 過去review bundleを再生成可能にする
- Git履歴を書き換えてファイルそのものを消去する
- runsやraw experiment dataを同時に整理する

Git historyとcleanup前tagがあるため、必要時には当時のコードを参照できる。

今回守るべきものは**コードではなく、結果・判断・科学的根拠**である。

# 最終方針

このcleanupは単純なファイル削除ではなく、

**Experiment → Result → Decision → Current Baseline**

という知識の流れを明示する作業として実施する。

今後は各Stage終了時に同じ処理を行い、実験専用コードやテストが永久に積み上がらない運用へ移行する。
