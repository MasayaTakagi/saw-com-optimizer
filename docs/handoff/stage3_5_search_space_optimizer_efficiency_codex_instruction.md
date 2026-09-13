# Stage 3.5 実験計画 / Codex 作業指示書
## Search-Space Design & Optimizer Efficiency Study

**対象プロジェクト:** `saw-com-optimizer`  
**対象ルート:** `C:\Users\sub\Documents\ChatGPT\saw-com-optimizer`  
**実行想定:** Codex / GPT-5.6 Luna / ExHigh  
**作成日:** 2026-09-12  
**位置づけ:** Stage 3.4b の 50 Ω `center_outer_same` convergence certification 完了後、20–200 Ω impedance sweep の前に実施する効率化研究

---

# 0. この指示書の目的

Stage 3.4b では、50 Ω / DMS / `center_outer_same` に対して 8 cold seeds を用いた強化 convergence certificate が **256k unique decoded evaluations/seed で成立した**。

したがって、次の課題は「さらに budget を増やせば収束するか」ではない。

次に解くべき課題は以下の2点である。

1. **探索空間の設計**
   - 現在の geometry bounds は必要以上に広くないか。
   - 実際に良解へ寄与する領域・変数・相関構造は何か。
   - 初期探索空間を安全に絞り、必要時のみ hard bounds まで拡張する方式で探索量を減らせないか。

2. **Optimizer の効率**
   - 256k/seed まで必要だった Legacy SciPy DE continuation を、そのまま impedance sweep の全点へ適用するのは重い。
   - 同じ最終品質・同じ convergence certificate を、より少ない unique evaluations で得られないか。
   - 既存の Legacy DE と既存 L-SHADE の効果を、探索空間の効果と混同せず比較する。

Stage 3.5 の最終目標は、**50 Ωで証明済みの解品質を落とさず、production optimization の代表的な収束コストを 256k から 128k 以下へ近づけること**である。

128k 以下は stretch target であり、最低合格基準は「品質非劣化を維持しながら unique evaluations を統計的・実務的に明確に削減できること」とする。

---

# 1. Source of truth

作業開始時には、古い Stage-number module や旧 root を source of truth にしない。

現在の canonical repository は:

```text
C:\Users\sub\Documents\ChatGPT\saw-com-optimizer
```

Final cutover 時点では Git root / source root / `.codex` root がこの場所に統一されている。

作業開始前に必ず以下を確認する。

```text
git rev-parse --show-toplevel
git status --short
git branch --show-current
git rev-parse HEAD
```

期待する top-level root:

```text
C:/Users/sub/Documents/ChatGPT/saw-com-optimizer
```

現在の source architecture では、chronological Stage number を新しい reusable Python source の名前に持ち込まない。

新しい実験 instance は config / experiment metadata / docs で Stage 3.5 と呼んでよいが、

```text
stage35_study.py
```

のような新しい source module は作らないこと。

必要な reusable behavior が既存 API にない場合のみ、現在の canonical architecture:

```text
src/sawopt/problem/
src/sawopt/optimizers/
src/sawopt/optimization/
src/sawopt/studies/
src/sawopt/reporting/
src/sawopt/io/
```

の適切な場所へ一般機能として追加する。

---

# 2. Stage 3.4b から引き継ぐ確定事項

Stage 3.5 は以下を再議論しない。

## 2.1 50 Ω baseline

固定条件:

```text
Rs = Rl = 50 Ω
topology = DMS
wiring = center_outer_same
```

`center_outer_same` は DMS の**配線方式**である。

探索自由度を減らす boolean や「center geometry = outer geometry」を意味するものとして再解釈してはいけない。

## 2.2 Stage 3.4b convergence

Stage 3.4b は 8 cold seeds で 256k checkpoint にて convergence certificate を成立させた。

Stage 3.5 ではこの 256k 結果を、

```text
current quality baseline
current convergence-cost baseline
```

として扱う。

512k へ延長して Stage 3.4b をやり直さない。

## 2.3 `io_idt_pairs`

Stage 3.4 / 3.4b で人工的 lower bound が問題になったため、`io_idt_pairs` は hard lower bound 8 を通常探索可能にした。

Stage 3.5 の search-space narrowing で、

```text
io_idt_pairs lower > 8
```

を安易に設定してはいけない。

少なくとも initial lower bound は 8 を維持する。

上側を狭める場合も Stage 3.4b evidence に基づき、hard upper bound は保持する。

## 2.4 convergence policy

Stage 3.4b の certificate gate を弱めない。

少なくとも以下の意味を維持する。

- 2 consecutive plateau intervals
- materially improving seed fraction gate
- seed IQR
- worst-minus-median
- late improvement
- validation gap
- micro-polish
- grid convergence
- pending stagnation recovery なし
- unresolved boundary pressure なし
- hard-bound state の整合
- budget / provenance / source hash / bundle integrity

Stage 3.5 の「効率化」のために convergence threshold を緩めることは禁止する。

---

# 3. 非交渉条件

Stage 3.5 では以下を変更しない。

- COM equations
- network equations
- COM parameter assumptions
- Band 28 specifications
- objective / validated rank semantics
- feasibility-first ordering
- wiring semantics
- 50 Ω termination
- dense/common validation の意味
- canonical integer decoding の意味
- unique decoded evaluation accounting
- Stage 3.4b convergence criteria
- physics tolerances

また、Stage 3.4b の best design / final population を、新しい cold-run の初期 population へ直接注入してはいけない。

Stage 3.4b data は、

```text
search-space diagnosis
initial-box design
target definition
```

には使用してよい。

しかし Stage 3.5 A/B run は cold-start とし、過去の solution vector を warm-start として使わない。

これにより、「良い初期解を知っていたから速くなった」効果と「探索戦略そのものが良くなった」効果を分離する。

---

# 4. Stage 3.5 の研究質問

Stage 3.5 は以下の4問に答える。

### Q1 — Search-space

Stage 3.4b の converged trajectories を見ると、各設計変数の良解は full hard bounds のどこに分布しているか。

### Q2 — Safe narrowing

良解分布から得た narrower initial bounds と、既存の boundary expansion を組み合わせることで、global optimum 候補を不当に除外せず探索効率を改善できるか。

### Q3 — Optimizer

同じ search space で比較したとき、既存 L-SHADE は Legacy SciPy DE より少ない unique evaluations で同等以上の validated rank に到達できるか。

### Q4 — Interaction

Optimizer の効率は search-space design に依存するか。

つまり、

```text
Legacy DE vs L-SHADE
```

だけではなく、

```text
full search space vs adaptive/narrow initial search space
```

との interaction を確認する。

---

# 5. 実験全体構成

Stage 3.5 は4フェーズとする。

```text
Phase A
Stage 3.4b offline diagnostics
        ↓
Phase B
safe initial search-space proposal
        ↓
Phase C
4-arm / 4-seed / 64k screening
        ↓
Phase D
baseline vs best strategy
8 fresh seeds / up to 256k certification
```

Phase A/B は既存 Stage 3.4b data の解析。

Phase C は development experiment。

Phase D は confirmatory experiment。

**Phase C の seed を Phase D の最終証明へ流用しない。**

---

# 6. Phase A — Stage 3.4b offline diagnostics

## 6.1 最初に Stage 3.4b artifact を特定する

ローカル repository / run / review bundle から Stage 3.4b の exact artifact を探す。

候補名:

```text
runs/next_50ohm_center_outer_same_stage34b
artifacts/review_bundles/
next_50ohm_center_outer_same_stage34b_review.zip
```

名前を推測して結果を再構築しない。

exact artifact を特定したら以下を検証する。

- exact merged config
- source hash / Git commit
- seed list
- requested / actual unique budgets
- final convergence status
- convergence checkpoint = 256k
- design-space versions
- active/hard bounds
- boundary events
- stagnation recovery events
- grid convergence
- final validated candidates

artifact 内の certificate と今回の前提が矛盾する場合は production run を開始せず、その差分をレポートする。

## 6.2 解析対象

各設計変数について最低限以下を抽出する。

- full hard bounds
- Stage 3.4b initial / active bounds
- final incumbent value per seed
- late-checkpoint incumbent values
- normalized distance to lower/upper hard bound
- normalized inter-seed spread
- IQR
- seed-to-seed range
- boundary event history
- duplicate/canonical-collapse indicators
- variable-to-variable rank correlation
- best objective / validated rank との関係

late checkpoint は artifact に存在するものを使い、原則:

```text
>= 128k
```

の evidence を優先する。

保存されていれば:

```text
128k
192k
256k
```

を最低限使用する。

## 6.3 Local sensitivity

Stage 3.4b の final validated design を使い、各変数の局所感度を測る。

ただし optimizer を回し直すのではなく、固定候補の近傍評価として行う。

### Integer variables

canonical design-space step を source から取得し、

```text
±1 step
±2 steps
```

を基本とする。

hard bound を越える perturbation は行わない。

### Continuous variables

full hard-range span に対して原則:

```text
±1 %
±2.5 %
±5 %
```

を候補とする。

geometry validation に反する場合はその点を invalid と記録する。

### 評価

同じ common/dense validation semantics を使う。

記録:

- feasibility
- max normalized violation
- sum normalized violations
- worst passband IL
- validated rank tuple
- per-spec normalized violations

単なる scalar objective だけで sensitivity を判断しない。

## 6.4 Pairwise relation

全変数の総当たり 2D sweep はしない。

次のどちらかに該当する上位最大3 pair のみ調査する。

- elite sample で強い rank correlation
- local perturbation で compensation が示唆される
- physical parameterization 上、明確に結合している

目的は surrogate model を作ることではなく、

```text
単独で狭めてよい変数
相関を保ったまま探索すべき変数
```

を区別することである。

---

# 7. Phase B — Safe initial search-space proposal

## 7.1 原則

Stage 3.5 では **hard physical bounds を狭めない**。

導入するのは:

```text
narrower initial bounds
+
automatic expansion toward existing hard bounds
```

である。

つまり search space は「削除」するのではなく、探索順序を変える。

これにより、過去の 50 Ω data への overfit で true optimum 候補を永久に除外する危険を抑える。

## 7.2 Initial bound の生成

各変数について Stage 3.4b late elite envelope を作る。

記号:

```text
Hlo, Hhi = original hard bounds
Elo, Ehi = late elite envelope
IQR      = late elite IQR
S        = Hhi - Hlo
```

guard band の初期規則:

```text
guard = max(0.10 * S, 1.5 * IQR, minimum_canonical_margin)
```

候補:

```text
Ilo = max(Hlo, Elo - guard)
Ihi = min(Hhi, Ehi + guard)
```

integer variable は canonical step に対して外向きに丸める。

minimum canonical margin は最低3 canonical steps とする。

ただし以下の条件では、その側を narrow しない。

1. elite が hard bound 近傍に集中している
2. Stage 3.4b で同じ側に boundary pressure があった
3. local sensitivity がさらに外側への改善を示唆する
4. elite distribution が明確に multimodal
5. normalized elite spread が大きい
6. evidence 数が不足

特に:

```text
io_idt_pairs initial lower = 8
```

は維持する。

## 7.3 Narrowing を採用する条件

候補 initial interval が full hard interval に対して十分な縮小にならない場合は無理に変更しない。

目安:

```text
initial width <= 0.70 * hard width
```

になった場合のみ search-space reduction として採用する。

それより広い場合は、その変数は full range のままとしてよい。

## 7.4 変数固定は禁止

Stage 3.5 では、感度が低く見える変数であっても定数へ固定しない。

variable elimination / dimension reduction は Stage 3.5 の結果を受けた次段階の候補であり、本実験では search-space narrowing と optimizer family の効果をまず測る。

---

# 8. Candidate strategy

Phase B 完了時に以下の2 search-space strategy を定義する。

## S0 — Full baseline

Stage 3.4b の production hard/initial search space をそのまま使う。

```text
S0 = current full production space
```

## S1 — Adaptive initial box

Phase B で決めた narrower initial bounds から開始し、既存 continuation boundary logic により必要時は hard bounds まで拡張可能とする。

```text
S1 = data-informed initial box
     + original hard bounds
     + boundary-driven expansion
```

S1 の config は Phase C 開始前に freeze し、hash を記録する。

Phase C/D の結果を見ながら S1 bounds を途中で変更してはいけない。

---

# 9. Optimizer arms

Optimizer は既に実装済みの2種類のみ比較する。

```text
O0 = Legacy SciPy DE continuation
O1 = L-SHADE
```

Stage 3.5 のために CMA-ES、Bayesian Optimization、surrogate optimizer を新規実装しない。

まず既存 optimizer と search-space design の interaction を評価する。

---

# 10. Phase C — 4-arm efficiency screening

Phase C は development screening であり、production convergence certificate ではない。

## 10.1 Arms

```text
A = S0 + O0 = full space     + Legacy DE   [baseline]
B = S1 + O0 = adaptive space + Legacy DE
C = S0 + O1 = full space     + L-SHADE
D = S1 + O1 = adaptive space + L-SHADE
```

## 10.2 Seeds

Stage 3.4b で使用した seed は使わない。

development seeds:

```text
20260917
20260918
20260919
20260920
```

全4 arm で同じ4 seedを使用する。

## 10.3 Budget

各 arm / seed:

```text
16k
32k
64k
```

64k で screening を終了する。

この Phase では 128k/256k へ自動延長しない。

## 10.4 Cold-start

全 arm cold-start。

禁止:

- Stage 3.4b best vector の注入
- Stage 3.4b population の再利用
- arm 間 population transfer
- neighbor warm start

## 10.5 保存する metric

各 checkpoint / seed / arm について:

- unique decoded evaluations
- objective calls
- valid physics evaluations
- cache hits
- duplicate rate
- solved frequency points
- search wall time
- validation wall time
- best validated rank
- max normalized violation
- sum normalized violation
- worst passband IL
- validation gap
- grid state
- boundary expansions
- recovery events
- population diversity diagnostics
- integer canonical-value diversity
- last significant improvement
- time/evaluations to target

---

# 11. Efficiency target の定義

Stage 3.4b 256k final result から以下を自動抽出する。

```text
T_best
T_median
T_worst
```

ここで T は final validated primary metric / rank information。

さらに Phase C の paired comparison 用として、

```text
time_to_T_median
evals_to_T_median
```

を計算する。

target 未達の場合は censored として扱い、単純に「64k」と置換しない。

可能なら survival-style summary か少なくとも:

```text
reached_target: true/false
first_reach_unique_evals
```

を保存する。

---

# 12. Phase C promotion rules

A は必ず baseline として残す。

B/C/D のうち Phase D へ進める variant は原則1つだけとする。

## 12.1 Search-space strategy B の評価

B は A に対して以下なら promotion candidate:

- 64k validated median が materially worse ではない
- 4 seed 中少なくとも 3 seed で品質が baseline と同等以上、または target 到達が早い
- reduced initial boundary で pressure が発生しても expansion が正常に機能
- permanent hard-bound exclusion がない
- duplicate/canonical collapse が悪化していない

## 12.2 L-SHADE の評価

C または D は対応する Legacy arm に対して以下のどちらかを満たせば promotion candidate:

1. 同等品質へ到達する median unique evaluations が 20%以上少ない
2. 同一64k budget で validated rank が materially better

L-SHADE は「新しいから」promotion しない。

## 12.3 Best variant selection

優先順位:

1. validated quality non-inferiority
2. target reach rate
3. median unique evaluations to target
4. worst-seed behavior
5. boundary/recovery stability
6. wall time

scalar search objective の最終値だけで winner を決めない。

## 12.4 Early rejection

variant が 64k 時点で:

- baseline より明確に悪い
- boundary expansion が頻発して initial-box の意味がない
- duplicate/canonical collapse が悪化
- validation instability が増加

した場合、その variant は Phase D へ進めない。

---

# 13. Phase D — Confirmatory efficiency certification

Phase D は、

```text
A = S0 + Legacy DE
```

と、

```text
V = Phase C で選ばれた best variant
```

の2-arm比較とする。

Phase C の seed は使用しない。

## 13.1 Fresh seeds

```text
20260921
20260922
20260923
20260924
20260925
20260926
20260927
20260928
```

8 cold seeds。

## 13.2 Checkpoints

```text
16k
32k
64k
96k
128k
192k
256k
```

Stage 3.4b と同様に checkpoint で convergence certificate を評価する。

ただし Stage 3.5 の目的は efficiency なので:

- 128k 以下で certificate 成立 → 強い成功
- 192k で成立 → 中程度の改善
- 256k で成立 → 品質は維持できるが convergence-budget 改善は限定的
- 256k 未収束 → variant 不採用

Stage 3.5 では 384k/512k へ自動延長しない。

256k を hard ceiling とする。

## 13.3 Paired design

A と V は全て同じ 8 seed を使用する。

seedごとに:

```text
A vs V
```

を paired comparison する。

---

# 14. Stage 3.5 合格基準

best variant を production candidate とするには、以下を全て満たすこと。

## Gate 1 — Correctness

- full regression PASS
- COM/network numerical core に意図的差分なし
- validated rank semantics unchanged
- convergence thresholds unchanged

## Gate 2 — Final quality non-inferiority

同一 confirmation seeds で variant が baseline に対して materially worse でない。

判定には Stage 3.4b で使用する material-improvement threshold の意味を再利用する。

少なくとも:

- median が materially worse でない
- worst-seed が悪化しすぎない
- >25% seeds が material degradation を示さない

## Gate 3 — Efficiency

最低条件:

```text
median unique evaluations to target
>= 30% reduction
```

推奨成功:

```text
>= 40% reduction
```

stretch target:

```text
約50% reduction
= 256k baseline → 128k 以下
```

## Gate 4 — Certificate

variant 自体が Stage 3.4b 相当の convergence certificate を成立させる。

単に target に早く到達しただけでは採用しない。

## Gate 5 — Robustness

- unresolved boundary pressure なし
- pending recovery なし
- grid convergence gate PASS
- validation gap PASS
- seed spread gate PASS
- hard-bound fallback が正しく動く

---

# 15. Secondary metrics

以下は winner 判定の補助情報であり、primary quality/certificate を上書きしない。

- wall time
- unique evaluations/sec
- objective calls / unique eval
- cache-hit rate
- duplicate rate
- population diversity
- frequency-point solves
- peak RSS
- worker utilization
- number of boundary expansions
- number of stagnation recoveries

wall time は machine load の影響を受けるため、

```text
unique decoded evaluations
```

を primary compute-efficiency metric とする。

---

# 16. 実装方針

## 16.1 まず既存機能を再利用

以下が canonical source に既に存在する場合は新規実装しない。

- initial / hard bounds
- boundary expansion
- continuation
- convergence certificate
- optimizer backend abstraction
- Legacy DE backend
- L-SHADE backend
- common validation
- review bundle
- seed-level parallelism

## 16.2 Source 追加が必要な場合

新しい reusable behavior のみ追加する。

想定例:

```text
reporting/search_space_diagnostics.py
```

または既存 reporting/analysis module の public function。

実験名固有の:

```text
stage35_*.py
```

は禁止。

## 16.3 Config

Stage 3.5 の chronology は config / experiments metadata に持たせる。

推奨例:

```text
experiments/stage3_5_search_efficiency/
    README.md
    screening.yaml
    confirmation.yaml
```

repository の現在の config convention が異なる場合は、既存 convention を優先する。

---

# 17. Tests

新規機能が必要な場合、最低限以下をテストする。

## Search-space

- initial bounds are inside hard bounds
- hard bounds remain unchanged
- integer initial bounds round outward correctly
- `io_idt_pairs` lower stays 8
- boundary pressure can expand S1 back toward hard bounds
- expansion increments design-space version
- convergence evidence resets when required
- no variable is accidentally frozen

## Diagnostics

- elite envelope is deterministic
- IQR/range calculations
- normalized boundary distance
- missing-history handling
- insufficient evidence causes “do not narrow”
- multimodal/edge cases fail safe toward full bounds

## Experiment isolation

- Stage 3.4b vectors are not inserted into cold populations
- same seed is reproducible within an arm
- arm labels/config hashes are saved
- Phase C and Phase D seed sets do not overlap

## Existing invariants

- fixed-seed reproducibility
- unique budget accounting
- canonical duplicate handling
- checkpoint resume
- feasibility-first comparator
- L-SHADE state/resume
- continuation boundary policy
- common dense validation
- source/provenance gate

---

# 18. Execution order for Codex

Codex は以下の順序で実行すること。

## Step 0 — Preflight

1. `AGENTS.md` を読む。
2. canonical root を確認。
3. dirty files を確認。
4. unrelated user changes を保持。
5. current HEAD/branch を記録。
6. Stage 3.4b artifact を特定。
7. Stage 3.4b certificate=256k を artifact から確認。
8. baseline test suite を実行。

baseline failure がある場合は今回の変更と混同せず記録する。

## Step 1 — Offline diagnostic

コード変更を最小限にして Phase A を実行。

生成:

```text
search_space_diagnostics.md
search_space_diagnostics.json
search_space_elites.csv
local_sensitivity.csv
pairwise_diagnostics.csv
```

## Step 2 — Freeze S1

diagnostics から S1 を機械的ルールで作る。

生成:

```text
search_space_s1.yaml
search_space_s1_rationale.md
```

S1 config hash を保存。

この時点以後 Phase C/D 中に S1 を変更しない。

## Step 3 — Implement only missing reusable support

必要な場合だけ実装。

targeted tests → full regression。

全 regression が PASS するまで production experiment を開始しない。

## Step 4 — Phase C screening

4 arms × 4 fresh seeds × max64k。

結果を自動集計。

best variant を promotion rule で1つ選ぶ。

明確な winner がなければ Phase D を無理に実行せず、`inconclusive` として review bundle を作成する。

## Step 5 — Phase D confirmation

baseline + best variant。

8 fresh seeds。

最大256k。

certificate 成立時点で arm 単位の early stop を許可する。

## Step 6 — Review bundle

self-contained review bundle を作成。

hash validation を実施。

## Step 7 — Final report

後述フォーマットで結果をまとめる。

---

# 19. Async orchestration

現在の async orchestration は production-candidate 状態である。

Stage 3.5 の長時間 run には canonical root の current orchestration を使用する。

最低限:

- duplicate process を作らない
- callback は1回
- lock leak なし
- resume target を記録
- source/config hash を freeze
- run directory を Git 管理へ入れない
- automatic next experiment を勝手に開始しない

`SessionStart Hook` の未解決事項を Stage 3.5 optimizer research と混ぜて追加開発しない。

明示 session / current working mechanism で production run が成立するなら、それを使用する。

---

# 20. Stop conditions

以下の場合は長時間 run を停止し、結果を報告する。

1. Stage 3.4b exact artifact を特定できない
2. Stage 3.4b certificate と「256k converged」が矛盾
3. COM/network numerical source に意図しない差分
4. full regression failure
5. S1 が hard bounds を恒久的に削除している
6. cold-start に過去 solution が混入
7. unique budget accounting が arm 間で一致しない
8. optimizer comparison で validation semantics が異なる
9. source/config hash が途中で変化
10. review bundle integrity failure

失敗を隠して別条件へ自動で進まない。

---

# 21. Codex がしてはいけないこと

- Stage 3.4b を 512k まで再実行する
- convergence threshold を緩める
- COM physics を変更する
- specification を緩める
- `center_outer_same` を geometry equality flag と解釈する
- 50 Ω best design を cold run の initial population へ直接入れる
- 50 Ωで得た narrow bounds を 20–200 Ω 全点へそのまま適用する
- Phase C seed で Phase D certificate を出す
- CMA-ES等を今回追加して scope を拡大する
- experiment のためだけに `stage35_study.py` を追加する
- old worktree / old root backup を削除する
- force push / history rewrite を行う
- Stage 3.5 完了後に自動で impedance sweep を開始する

---

# 22. 最終成果物

最低限以下を残す。

```text
docs / experiment README
exact merged configs
Stage 3.4b baseline extraction
search-space diagnostics
S1 rationale
Phase C arm summaries
Phase D paired comparison
checkpoint data
convergence certificates
resource/runtime metadata
test logs
git diff/status/HEAD
source/config hashes
review bundle
final report
```

review bundle の推奨名:

```text
stage3_5_search_space_optimizer_efficiency_review.zip
```

run naming は repository の既存規則に従う。

---

# 23. Final report format

Codex の最終報告は最低限以下を含める。

## A. Baseline

```text
Stage 3.4b:
status
convergence checkpoint
8-seed summary
final validated quality
```

## B. Search-space diagnosis

変数ごとに:

```text
hard bounds
elite range
IQR
boundary evidence
local sensitivity
S1 initial bounds
narrowing rationale
```

## C. Phase C

表:

```text
arm
optimizer
search-space strategy
seed count
64k validated median
worst
target reach count
median evals-to-target
duplicate rate
boundary events
```

## D. Phase D

paired seed table:

```text
seed
baseline first target eval
variant first target eval
baseline final rank
variant final rank
baseline convergence checkpoint
variant convergence checkpoint
```

## E. Decision

以下のいずれかを明示:

```text
PROMOTE_S1_LEGACY
PROMOTE_S0_LSHADE
PROMOTE_S1_LSHADE
KEEP_CURRENT_BASELINE
INCONCLUSIVE
```

## F. Next recommendation

Stage 3.5 の結果からのみ判断し、

- impedance screening へ進む
- search-space design をさらに改善
- mixed-discrete optimizer を次段で検討

のどれかを提案する。

**自動実行はしない。**

---

# 24. Stage 3.5 後の decision tree

## Case A — S1 + Legacy DE が勝つ

探索空間設計が主な bottleneck だったと判断。

次の impedance study では Legacy DE を維持しつつ、

```text
broad screening
→ data-informed initial box
→ boundary-expandable deep certification
```

へ進む。

ただし 50 Ω S1 bounds を他の Z に固定適用しない。

## Case B — L-SHADE が勝つ

optimizer family の変更が効いたと判断。

confirmation で certificate が成立していれば、次の impedance screening の標準候補とする。

Legacy DE は reference backend として残す。

## Case C — S1 + L-SHADE が勝つ

探索空間と optimizer の interaction が大きい。

この組み合わせを次段の production candidate とする。

## Case D — どれも baseline を明確に上回らない

256k は current problem の実質的コストである可能性がある。

力任せに512kへ増やすのではなく、次の研究対象を:

```text
mixed-discrete search
variable grouping
hierarchical parameterization
integer-aware mutation/refinement
```

へ移す。

## Case E — Search-space narrowing で品質が落ちる

S1 を不採用。

「Stage 3.4b の良解分布だけでは safe narrowing を一般化できない」という重要な negative result として保存する。

---

# 25. この実験の成功定義

Stage 3.5 は「必ず新Optimizerを採用する」ことが成功ではない。

成功とは以下である。

1. Stage 3.4b の converged data から search-space structure を定量化できた。
2. search-space effect と optimizer effect を分離して比較できた。
3. fresh seeds で再現性を確認した。
4. 256k baseline に対する eval-efficiency を定量化した。
5. 品質を犠牲にした見かけ上の高速化を排除した。
6. 次の impedance sweep に採用する production strategy を evidence に基づいて決められる。

この結果を得てから、20–200 Ω impedance screening / certification 設計へ進む。
