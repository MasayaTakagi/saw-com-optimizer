# Codex 作業指示書
## Stage 3.6 Gate 2C — Joint Impedance / DOF Fast Screening

## 0. Mission

Stage 3.6 Gate 2B-Bの結果を受け、DMS単体についてインピーダンスと設計自由度の関係を軽量に同時スクリーニングする。

本作業は最終optimizationではない。

目的は、

- 追加DOFに計算資源を投入する価値があるか
- 62.5/62.5、100/100、50/75を引き続き追う価値があるか
- hard-bound pressureが構造的に残るか
- DMS単体を一旦closeしてhybrid topologyへ移れるか

を高速に判断できるreview bundleを作ることである。

**過剰な追加実験を行わないこと。**

---

# 1. Start-up audit

最初に現在repositoryを確認し、以下を記録する。

- git branch
- git HEAD
- git status
- relevant config paths
- canonical search-space registry/path
- Gate 2B-B config path/hash
- current release group = `G1_G2`
- current dimension
- current hard/active bounds
- optimizer backend/version

Gate 2B-B成果物を改変しない。

---

# 2. Search-space audit

## 2.1 S0

現在の `G1_G2` をS0とする。

挙動を変更しない。

## 2.2 S1 candidate discovery

canonical search-space registryを調査し、`G1_G2` の次に使用可能な最小release groupを特定する。

条件:

- existing implementation
- geometry/evaluator対応済み
- manufacturing/layout validation対応済み
- COM physicsの新規仮定不要
- 原則1～2 DOF追加

既存の `G1_G2_G3` などがあるならそれを優先する。

## 2.3 Prohibited DOF

以下を新規releaseしてはならない。

- `metallization_ratio`
- `thickness_over_lambda`

COM calibrationなしの物理依存性を新たに仮定しないこと。

## 2.4 io_idt_pairs

`io_idt_pairs=8` はhard lower limitとして維持する。

**8未満へ変更禁止。**

hard boundをsoft bound扱いに変更してはならない。

## 2.5 Fallback

canonicalな次release groupが存在しない場合:

1. `center_aperture_um` が既に実装・decode・evaluation・validation対応済みか確認
2. 対応済みなら追加1 DOF候補とする
3. 未対応なら新規physics実装は行わない

安全なS1を構成できない場合:

- production optimizationを開始しない
- audit結果
- blockers
- recommended next action

をまとめてreview bundleを作り、

`STAGE3_6_GATE2C_DOF_AUDIT_STOP`

で停止する。

---

# 3. Sensitivity preflight

S1を構成した場合、production前に小規模preflightを行う。

追加DOFそれぞれについて、

- lower / center / upper付近の合法値
- 少なくとも2つのimpedance条件

でresponseを評価し、

- decoded designが変化する
- numerical responseが変化する
- validation pathに伝搬する
- cache key/canonicalizationがDOFを区別する

ことを確認する。

responseが実質不変のdummy DOFをreleaseしてはならない。

preflight failure時はproductionへ進まない。

---

# 4. Test policy

今回の目的は高速screeningである。

### Source changeなし / config-onlyの場合

- relevant targeted tests
- search-space decode/evaluation smoke
- one short optimizer smoke

でよい。

不要なfull regressionをproduction前に毎回走らせない。

### Source code変更が必要な場合

- changed moduleのtargeted tests
- related search-space/evaluator tests
- full regression

を実施する。

source changeが必要になった理由をsummaryに明記する。

---

# 5. Experiment matrix

## Impedance conditions

| ID | Zin | Zout |
|---|---:|---:|
| I0 | 50.0 | 50.0 |
| I1 | 62.5 | 62.5 |
| I2 | 100.0 | 100.0 |
| I3 | 50.0 | 75.0 |

## Search spaces

- S0 = current `G1_G2`
- S1 = minimal next safe geometric release

## Seeds

基本:

- 20260917
- 20260918

## Budget

- 16,000 unique evaluations / run
- cold start
- warm start disabled

## Checkpoints

- 4,000
- 8,000
- 12,000
- 16,000

## Base run count

`4 impedance × 2 search spaces × 2 seeds = 16 runs`

Nominal evaluations:

`256,000`

---

# 6. Execution invariants

以下はGate 2B-Bと同一に保つ。

- optimizer family / production L-SHADE
- objective
- feasibility-first/final ranking semantics
- constraints
- common validation grid policy
- termination interpretation
- topology = DMS only
- wiring / structural family used by Gate 2B-B
- cold start semantics

S0/S1比較以外の変数を不用意に変えない。

---

# 7. Optional third-seed promotion

基本16 runs終了後に自動判定する。

seed `20260919` を追加できるcellは最大4つ。

cell = `(impedance condition, search space)`。

promotion候補条件:

### Rule A
同一impedanceでS1がS0より両seedで良い。

### Rule B
一方のseedでS1が0.015以上改善し、
もう一方のregressionが0.005以下。

### Rule C
そのcellが全cell中のabsolute best候補。

### Rule D
search-space変更でimpedance rankingが明確に反転し、
設計判断に重要。

候補が4つを超える場合、優先順:

1. absolute best
2. 62.5/62.5関連
3. S1 improvement magnitude
4. asymmetric 50/75
5. 100/100
6. 50/50

追加runも16k budgetとする。

最大追加:

`4 × 16k = 64k`

本Gate全体のnominal upper limit:

`320k evaluations`

**第三seedを全cellへ追加禁止。**

---

# 8. Boundary diagnostic

optimization終了後にbest designsへcheap diagnosticを実施する。

## 8.1 io_idt_pairs

bestが `io_idt_pairs=8` の場合:

- original
- io_idt_pairs = 9
- io_idt_pairs = 10

を同一designの他変数固定でcommon validation grid評価する。

8未満は評価禁止。

## 8.2 reflector_electrodes

bestがlower hard boundの場合、

canonical discrete ruleに従い内側へ2 step評価する。

例:

- 40
- 42
- 44

ただし実装のvalid stepが異なる場合はcanonical ruleを使用する。

## 8.3 Other boundaries

追加DOFを含め、normalized distanceが非常に小さい変数は記録する。

hard bound外は探索しない。

## 8.4 Boundary classification

- inward moveで悪化 → `persistent_hard_boundary_pressure`
- inward moveで改善 → boundary hitは偶然/optimizer artifactの可能性
- mixed → `inconclusive`

と記録する。

boundary probe結果をoptimization rankingへ混ぜない。

---

# 9. Required analysis

## 9.1 Search-space paired comparison

同一impedance・同一seedで、

`delta_space = S1.max_violation - S0.max_violation`

を算出。

保存:

- seed-wise delta
- mean/median delta
- sign consistency
- relative improvement %

## 9.2 Impedance comparison

S0内、S1内を別々に比較する。

最低限:

- 50/50
- 62.5/62.5
- 100/100
- 50/75

のprimary metricを表にする。

## 9.3 DOF utilization

S1追加DOFごとに:

- best values
- normalized positions
- boundary distance
- seed dispersion
- condition dependence

を集計。

## 9.4 Convergence-lite

convergence certificateは不要。

ただし各runについて:

- 4k
- 8k
- 12k
- 16k
- last meaningful improvement
- improvement after 90% budget

を保存する。

目的は明らかなunderoptimization flagのみ。

## 9.5 Constraint bottleneck

- active limiting constraint
- stopband
- IL
- input/output VSWR
- feasibility

を条件ごとに集計。

---

# 10. Decision labels

各impedanceについてsearch-space effectを以下に分類する。

### `DOF_BENEFIT_STRONG`

目安:

- S1が複数seedで一貫改善
- absolute improvement ≳ 0.01 または relative ≳ 2%

### `DOF_BENEFIT_WEAK`

- 改善方向は一致するが小さい
- またはthird seedが必要な程度のばらつき

### `NO_MATERIAL_DOF_BENEFIT`

- |delta|が概ね0.005未満
- 追加DOFがほぼ利用されない

### `DOF_IMPEDANCE_INTERACTION`

- impedanceによってS1効果の符号/大きさが大きく異なる

### `INCONCLUSIVE`

- seed reversalが大きい
- late improvementが強い
- numerical/geometry issueが残る

これらはscreening labelであり、統計的有意差を主張しない。

---

# 11. Required output files

最低限以下を作る。

## Data

- `all_seed_results.csv`
- `search_space_comparison.csv`
- `impedance_comparison.csv`
- `dof_utilization.csv`
- `boundary_probe_results.csv`
- `convergence_lite.csv`
- `constraint_bottleneck_summary.csv`
- `promotion_decisions.csv`

## Metadata / config

- `experiment_manifest.json`
- exact S0 search-space snapshot
- exact S1 search-space snapshot
- merged experiment config
- reproduction metadata
- git head / branch / status / diff summary
- test command/result

## Markdown

- `stage3_6_gate2c_fast_screen_summary.md`
- `test_summary.md`

## Plots

最低限:

1. S1-S0 delta by impedance
2. max violation scatter by impedance/search-space
3. added DOF utilization
4. boundary probe comparison

plot数を不要に増やさない。

---

# 12. Final summary requirements

`stage3_6_gate2c_fast_screen_summary.md` には以下を必ず記載する。

1. S0の定義
2. S1の定義と追加DOF
3. S1を安全と判断した根拠
4. 基本run完走数
5. promoted third-seed run
6. 各impedanceでのS1-S0効果
7. impedance rankingの変化
8. DOF utilization
9. hard-bound pressure
10. active constraint
11. feasible count
12. obvious underoptimization flags
13. DMS単体をさらに深掘りする価値
14. hybridへ進むことを妨げるblockerの有無
15. unresolved ambiguity

以下のような断定は禁止:

- global optimum
- final optimal impedance
- statistically significant

今回の目的はpreliminary screeningである。

---

# 13. Hard stop

以下を開始してはならない。

- 32k/64k full confirmation
- 5-seed全条件確認
- io_idt_pairs < 8
- uncalibrated metallization/thickness optimization
- hybrid topology production optimization
- ladder resonator optimization
- next stageの自動実行

全解析とreview bundle作成後、

`STAGE3_6_GATE2C_FAST_SCREEN_COMPLETE_STOP`

と出力して停止する。

---

# 14. Review philosophy

曖昧さをゼロにするための追加計算は行わない。

判断に十分な方向性が得られれば、それをsummaryに残して先へ進む。

後続hybrid studyで問題になった曖昧点のみ、必要な時点で追加実験する。

本Gateの成功は「最適値を確定すること」ではなく、

> 次に何を検討する価値が高いかを、少ない計算量で明確にすること

である。
