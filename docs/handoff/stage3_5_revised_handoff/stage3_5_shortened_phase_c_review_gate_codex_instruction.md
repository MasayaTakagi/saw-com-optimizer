# Stage 3.5 短縮版 作業指示書
## Search-Space / Optimizer Efficiency Study with Mandatory Phase-C Review Gate

**対象プロジェクト:** `saw-com-optimizer`  
**Canonical root:** `C:\Users\sub\Documents\ChatGPT\saw-com-optimizer`  
**実行想定:** Codex / GPT-5.6 Luna / ExHigh  
**位置づけ:** Stage 3.4b convergence certification 後、impedance sweep 前の効率化研究  
**重要:** **Phase C 完了後に必ず停止し、review bundleを作成して人間レビューを待つ。Phase Dは自動開始禁止。**

---

# 0. 目的

Stage 3.4b では 50 Ω / DMS / `center_outer_same` に対し、8 cold seeds で 256k unique decoded evaluations/seed にて収束証明が成立した。

Stage 3.5 では、

1. search-space design の改善
2. Legacy DE / L-SHADE の効率比較
3. 256k baseline より少ない evaluation で同等品質へ到達可能か

を検証する。

ただし、Stage 3.4b が約5時間規模だったため、今回のStage 3.5は**証拠強度を落としすぎず、典型的に5〜8時間程度へ収める**ことを狙う。

そのため、

- Phase C は逐次淘汰方式
- Stage 3.4b baseline は再利用
- Phase D はwinnerのみ8 fresh seeds
- 256k自動延長はしない
- Phase C完了後に必ずレビュー停止

とする。

---

# 1. 非交渉条件

以下は変更禁止。

- COM equations
- network equations
- evaluator physics
- Band 28 specs
- feasibility-first ordering
- convergence thresholds
- certificate thresholds
- integer decoding semantics
- hard physical bounds
- `center_outer_same` wiring semantics
- Stage 3.4b の「256kでconverged」という科学的結論
- cold-start原則
- parity tolerance

parityや高速化のために閾値を緩めてはいけない。

---

# 2. 作業開始前

canonical root:

```powershell
cd C:\Users\sub\Documents\ChatGPT\saw-com-optimizer
```

確認:

```powershell
git rev-parse --show-toplevel
git status --short
git branch --show-current
git rev-parse HEAD
```

`AGENTS.md` を読む。

unrelated user changes は保持する。

前回までのStage 3.5 corrective changesが既に入っていることを確認し、同じpatchを再適用しない。

---

# 3. まず完了させる修正

Phase C再実行前に、前回レビューで特定したvalidation semantics問題を修正する。

## 3.1 historical dense validationをsource of truthにする

Stage 3.4b historical recordには、

- top-level search/adaptive-grid record
- nested `validation_record`

の2つがある。

Stage 3.5 のhistorical quality analysisでは、

```text
record["validation_record"]
```

をdense-validation source of truthとして使用する。

top-level `validated_rank_tuple` はprovenance用に保持するが、dense parity / elite / local sensitivityの基準にはしない。

---

# 4. Cross-version parity gate

各Stage 3.4b final designについて、

```text
historical validation_record rank
vs
current code re-evaluation rank
```

を同じ保存済みvalidation frequency grid上で比較する。

保存:

```text
historical_search_rank
historical_validation_rank
current_validation_rank
max_abs_validation_rank_diff
validation_parity_pass
```

tolerance:

```text
rtol = 1e-9
atol = 1e-10
```

変更禁止。

合格条件:

```text
8 / 8 seeds PASS
```

期待値としてレビューでは max diff = 0.0 が確認済みだが、ハードコードしない。

8/8 PASSでなければPhase Cへ進まない。

---

# 5. Search-space diagnostics

late evidence:

```text
128k
192k
256k
```

を使用。

elite orderingはhistorical nested `validation_record` rankで行う。

local sensitivityも、

```text
baseline dense validation
vs
perturbation dense validation
```

を同一保存grid上で比較する。

hard-bound外perturbationは改善証拠として扱わない。

S1生成規則は従来どおり保守的に行う。

- hard bounds unchanged
- no variable fixed
- `io_idt_pairs` lower = 8
- boundary expansion preserved

S1生成後にhashをfreezeする。

---

# 6. Stage 3.5 common-grid target

Phase Cのefficiency比較では、historical saved rankをそのままtargetに使わない。

Phase C完了後、以下すべてから1つのcommon validation gridを構築する。

```text
Stage 3.4b final 8 designs
+
Phase C surviving/current arm checkpoint designs
```

同一grid上で:

- Stage 3.4b final 8 designs
- Phase C arm designs

を再評価する。

Stage 3.4b 8 designsから:

```text
T_best_common
T_median_common
T_worst_common
```

を定義する。

保存:

```text
baseline_common_grid_rows.csv
baseline_common_grid_targets.json
common_validation_grid metadata
grid_id
```

armごとに別gridを作らない。

---

# 7. Phase C — 短縮版 Screening

Phase Cは2段階に分ける。

## Arms

```text
A = S0 + Legacy DE
B = S1 + Legacy DE
C = S0 + L-SHADE
D = S1 + L-SHADE
```

## Seeds

全arm共通:

```text
20260917
20260918
20260919
20260920
```

cold-start。

Stage 3.4b vector/populationを注入しない。

---

# 8. Phase C-1 — 全4 armを32kまで

全arm:

```text
16k
32k
```

まで実行。

32k終了時点でfutility判定を行う。

### 32k futility criteria

candidate armを64kへ延長しない条件の例:

- 4 seed中3 seed以上でbaseline Aよりmaterially worse
- target方向への改善傾向が明らかに弱い
- duplicate/canonical collapseが明確に悪い
- S1でboundary expansionが頻発しinitial-box効果が実質ない
- validation instabilityが増えている
- obvious optimizer failure

ただし32k時点で差が曖昧なら**落とさない**。

短時間化のために不確実なarmを強引に切らない。

---

# 9. Phase C-2 — survivorsのみ64kへ

必ずA baselineは64kまで残す。

32kで生き残った candidate のみ:

```text
64k
```

へ延長する。

最大:

```text
A + 1〜3 candidates
```

。

64k完了後、common validation gridを構築し、Stage 3.4b baselineを含めて全比較をやり直す。

---

# 10. Phase C winner selection

優先順位:

1. validated quality non-inferiority
2. T_median_common reach rate
3. median unique evaluations to target
4. worst-seed behavior
5. boundary/recovery stability
6. duplicate/canonical diversity
7. wall time

scalar optimizer objectiveだけでwinnerを決めない。

L-SHADEがwinner候補の場合は、

```text
certificate evidence capability
```

を確認する。

必要なevidenceをPhase Dで生成できないなら、L-SHADEを自動promotionしない。

---

# 11. Mandatory Phase-C Review Gate

**ここが最重要。**

Phase Cが完了したら、Codexは必ず停止する。

Phase Dを自動開始してはいけない。

以下のreview bundleを作成する。

推奨名:

```text
stage3_5_phase_c_review.zip
```

最低限含める:

```text
REVIEW_ME.md
git HEAD / status
source hash
config hashes
S1 hash
Stage 3.4b artifact hash
parity report
search-space diagnostics
S1 rationale
Phase C-1 results
futility decisions
Phase C-2 results
common validation grid metadata
baseline_common_grid_rows.csv
baseline_common_grid_targets.json
A/B/C/D checkpoint data
arm summaries
winner recommendation
L-SHADE certificate readiness
runtime/resource summary
test logs
manifest with hashes
```

---

# 12. Phase-C REVIEW_ME.md 必須内容

Codexは以下を明示する。

## A. Parity

```text
8/8 PASS?
max diff
artifact hash
```

## B. S1

```text
which variables changed
initial bounds
hard bounds unchanged?
expansion preserved?
```

## C. Phase C-1

表:

```text
arm
32k median quality
worst seed
target trend
duplicate rate
boundary events
futility decision
```

## D. Phase C-2

表:

```text
arm
64k median validated rank
target reach count
median evals to target
worst seed
validation gap
boundary/recovery status
```

## E. Common-grid baseline

```text
grid_id
T_best_common
T_median_common
T_worst_common
```

## F. Winner recommendation

以下のいずれか:

```text
A
B
C
D
INCONCLUSIVE
```

## G. Phase D readiness

```text
winner certificate capable?
recommended max budget: 128k or 192k
estimated runtime
```

## H. Explicit stop line

最後に必ず:

```text
PHASE_C_COMPLETE_WAITING_FOR_REVIEW
```

と書く。

---

# 13. Phase C後の動作禁止

review bundle作成後は:

- Phase D開始禁止
- fresh confirmation seeds使用禁止
- 192k/256k延長禁止
- impedance sweep開始禁止
- winner configのproduction化禁止

ユーザー/ChatGPTから新しい明示指示が来るまで停止。

---

# 14. Phase D — レビュー後のみ実施

この章は将来のために定義するが、**Phase Cレビュー前には実行禁止**。

Phase Dはwinner strategyのみ本格run。

## Winner seeds

fresh 8 seeds:

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

cold-start。

---

# 15. Phase D-1 — 128kを第一目標

winnerを:

```text
64k
128k
```

まで実行。

128kで以下を判定:

- Stage 3.4b相当certificate
- common-grid quality non-inferiority
- seed spread
- grid convergence
- validation gap
- no pending boundary
- no pending recovery
- efficiency target

128kで全てPASSならwinner側の本格計算を終了する。

---

# 16. Phase D-2 — 必要時のみ192k

128kで未達だが改善継続が妥当な場合のみ:

```text
192k
```

へ延長。

192kでcertificate PASSなら終了。

192kで未収束または品質改善が限定的なら、

```text
KEEP_CURRENT_BASELINE
```

または

```text
INCONCLUSIVE
```

とする。

---

# 17. 256kは通常ルートから外す

Stage 3.5の目的は256k baselineより明確に効率化できるかを見ること。

したがってPhase D winnerを自動で256kへ延長しない。

192kまでで効率改善を証明できなければ、今回のStage 3.5としては十分な高速化が得られなかったと判断する。

256kが必要かどうかは別レビュー後の追加判断とする。

---

# 18. Baseline再実行の短縮

Phase DでLegacy baselineを8 fresh seeds × 256kまで再実行しない。

Stage 3.4b exact artifactをreference baselineとする。

Stage 3.4b final/checkpoint designsをPhase D common grid上で再評価して比較する。

winnerが128kまたは192kで合格しそうな場合のみ、必要に応じて:

```text
Legacy baseline
4 fresh seeds
same max budget as winner
```

のaudit runを追加する。

これはPhase Cレビュー後の判断事項。

Codexが自動でauditを開始しない。

---

# 19. 期待実行時間

実測:

```text
Stage 3.4b ≈ 5h48m
Phase C A-arm 4 seeds × 64k ≈ 47m
```

今回の短縮版の目安:

```text
Phase A/parity/S1     10〜30 min
Phase C               2〜3 h typical
Phase C review stop   mandatory
Phase D 128k          2〜4 h typical
Phase D 192k          3〜5 h typical
```

Stage 3.5全体:

```text
typical 5〜8 h
harder case 7〜9 h
```

ただしPhase Cレビューを挟むため、Phase C完了時点で一度停止する。

---

# 20. L-SHADE certificate readiness

L-SHADEがPhase C winner候補の場合、最低限以下のevidenceをPhase Dで生成可能であることを確認。

```text
grid_converged
recovery_pending_confirmation
boundary_pending_confirmation
hard_bound_unresolved
micro_polish_improvement
fraction_of_budget_at_last_significant_improvement
validation_gap_primary
```

missing evidenceをdefault値で埋めてPASS扱いしない。

capability不足ならPhase C reportで:

```text
BLOCKED_CERTIFICATE_READINESS
```

を明示する。

---

# 21. Tests

Phase C再実行前に:

```powershell
python -m pytest tests/unit/reporting/test_search_space_diagnostics.py -q
python -m pytest tests/unit/studies/test_search_efficiency.py -q
python -m pytest tests/unit/optimization/test_stage34b_convergence.py -q
python -m pytest -q
```

全PASS必須。

Windows console patchを含む場合:

```powershell
python -m pytest tests/unit/orchestration/test_worker.py -q
python -m pytest tests/unit/orchestration/test_process_runner.py -q
```

---

# 22. Stop conditions

以下の場合はPhase Cを開始/継続しない。

1. Stage 3.4b artifact hash mismatch
2. historical `validation_record` missing
3. 8/8 dense parity PASSにならない
4. tolerance変更が必要
5. full regression failure
6. hard bounds changed
7. S1 variable frozen
8. A/B/C/D source hash mismatch
9. common-grid target不成立
10. armごとに別grid
11. Phase C review bundle integrity failure

---

# 23. Phase C review後のdecision tree

ChatGPTレビュー後、次のいずれかを選ぶ。

## Case A — 明確なwinnerあり / certificate capable

Phase Dへ進む。

winnerのみ8 fresh seeds。

128k → 必要時192k。

## Case B — Legacy baselineが最良

Phase Dは原則不要。

Stage 3.5は、

```text
KEEP_CURRENT_BASELINE
```

として終了候補。

## Case C — L-SHADEが速いがcertificate incapable

Phase Dへ進まない。

まずcertificate evidence implementationを追加。

## Case D — S1効果なし

「search-space designが無効」と一般化しない。

今回のS1だけで効果が限定的だったと解釈。

## Case E — 結果が接戦

Phase D winnerを無理に1つに決めず、追加小規模comparisonをレビュー後に設計する。

---

# 24. Codex最終出力 — 今回はPhase Cまで

今回Codexが最終的に返すstatusは原則:

```text
PHASE_C_COMPLETE_WAITING_FOR_REVIEW
```

または問題があれば:

```text
BLOCKED_PARITY
BLOCKED_REGRESSION
BLOCKED_CERTIFICATE_READINESS
INCONCLUSIVE
```

**Phase Dの完了報告は今回の作業範囲外。**

---

# 25. 成功条件

今回の作業成功は:

1. historical dense semanticsが統一される
2. 8/8 parity PASS
3. S1がcorrect evidenceから再生成される
4. Phase C 4-arm screeningが32kまで公平に実施される
5. futility ruleで安全にsurvivorsを絞る
6. survivorsのみ64kへ延長される
7. Stage 3.4b baselineと全armが同じcommon gridで比較される
8. winner recommendationが生成される
9. L-SHADE certificate readinessが確認される
10. review bundleを作成
11. **Phase Dを開始せず停止**
12. ChatGPTレビューを挟める状態になる

これを満たしたら今回のCodexタスクは完了とする。
