# Stage 3.2 実験計画 — 50 Ω DMS optimizer validation

## 目的

Stage 3.2 の目的は、50 Ω・DMS 1段について、

1. optimizer が十分探索したか、
2. 探索境界が解を人工的に制限していないか、
3. その上でなお仕様未達なら、現行仮COMモデル＋DMS設計空間の限界と判断できるか、

を再現可能な形で判定することである。

高速化は optimizer の意味を変えない範囲だけ実施する。低レベルなCOM高速化、GPU化、Numba化等は Stage 3.2 の対象外とする。

---

# Phase 0 — 実装前準備

## 0.1 Source of truth

- 現在の実装済み Stage 3.1 ソースを source of truth とする。
- 以前の Stage 1 / Stage 2 / Stage 3 handoff は設計意図の参照に留め、古い patch を機械的に再適用しない。
- 現行テストを全て通してから変更開始する。

## 0.2 対象 benchmark

最初の本番対象は 50 Ω DMS-only とし、wiring を分離する。

- `outer_ports`
- `center_outer_same`

`DMS 1段の限界` と `特定wiringの限界` を混同しない。

---

# Phase 1 — optimizer correctness 実装

## 1.1 Budget continuation

現在の 500 / 1000 / 2000 / 4000 / 8000 を独立再スタートとして扱わず、各 seed ごとに 1 本の探索 trajectory とする。

例:

```text
cold start
  ↓
500 unique decoded designs
  ↓ checkpoint + validation
1000
  ↓ checkpoint + validation
2000
  ↓ checkpoint + validation
4000
  ↓ converged ? stop : continue
8000
```

### 必須条件

- 500→1000 等で optimizer population / best / RNG trajectory を原則維持する。
- budget checkpoint は観測点であり、探索のリセット点ではない。
- `requested_unique_budget` と `actual_unique_design_evaluations` を必ず保存する。
- adaptive-frequency grid が収束しても、design budget が残っていれば同じ grid 上で探索を継続する。
- frequency-grid convergence と design-optimization convergence を別状態として扱う。

## 1.2 8000 auto escalation

設定例:

```yaml
budgets: [500, 1000, 2000, 4000]
optional_max_budget: 8000
auto_escalate: true
```

4000 で `converged` でなければ 8000 へ同一 trajectory のまま自動継続する。

## 1.3 Adaptive grid と継続探索

周波数 grid 更新時:

1. current population を保持する。
2. 新しく追加された frequency のみ incremental COM evaluation を行う。
3. current population の objective / constraint metrics を更新する。
4. 同じ population で探索を継続する。

同じ geometry の再評価は `unique_design_evaluations` に加算しない。`solved_frequency_points` のみ加算する。

## 1.4 Convergence 判定

同一 seed の paired budget comparison を用いる。

主要指標:

- `best_primary_metric`
- `median_primary_metric`
- seed IQR
- paired median improvement
- paired improvement IQR
- significant-improvement seed count
- `last_significant_improvement_unique_eval`
- `fraction_of_budget_at_last_significant_improvement`
- common-dense validation gap
- best-candidate polish improvement

### Converged の基本ルール

同一 design-space version 内で、連続 2 budget interval が plateau であることを要求する。

初期推奨閾値:

- paired median primary improvement < 2%
- final seed IQR < 0.1 primary-metric equivalent
- common validation gap < 0.02
- best-candidate polish improvement < 0.02
- 最後の 25% budget 内に significant improvement がない

閾値は config 化する。

## 1.5 Micro-polish

checkpoint 中間点の polish は診断用コピーで実施し、DE trajectory へ戻さない。

最終停止時のみ:

```text
DE final candidate
  ↓
common dense validation
  ↓
mixed discrete/continuous polish
  ↓
common dense revalidation
  ↓
改善した場合のみ polished design を最終採用
```

記録を分離する。

- `best_candidate_polish_improvement`
- `median_candidate_polish_improvement`
- `polish_evaluations`

convergence gate には best candidate の値だけを使用する。

---

# Phase 2 — 自動探索境界診断・拡張

## 2.1 Soft bound / hard bound

各最適化変数を以下に分ける。

- initial/soft bounds: optimizer が開始時に使う範囲
- hard bounds: 物理・製造上の絶対限界
- `expandable`: 自動拡張可否

例:

```yaml
io_idt_pairs:
  initial: [20, 100]
  hard: [8, 120]
  expandable: true
  lower_steps: [15, 10, 8]
```

hard bounds は自動変更禁止。

## 2.2 Boundary pressure 判定

1 seed の best が境界に来ただけでは拡張しない。

チェックポイントで複数seedを coordinator が集約し、以下を見る。

- best 候補の boundary hit rate
- 各seed上位候補群の boundary concentration
- 直近複数checkpointでの持続性
- boundary方向に改善する傾向

推奨初期条件:

- 5 seeds 中 4 seeds 以上が boundary または boundary+1以内
- 上位候補の 50% 以上が boundary neighborhood
- 2 checkpoint 連続で同傾向

## 2.3 Boundary probe

拡張前に安価な probe を行う。

例: lower bound = 20 の場合、hard bound が許せば 18 / 16 等を局所試験する。

- probe で primary metric が意味のある改善 → expand
- 改善なし → bounds維持

probe は polish infrastructure を再利用してよい。

## 2.4 Bound expansion

- 自動縮小は禁止。
- 拡張は段階的に行う。
- design-space version を increment する。
- convergence plateau history をリセットする。
- 既存 population を保持しつつ、新しく開いた領域へ 10–25% exploration injection を行う。

例:

```text
version 1: io pairs 20–100
  ↓ strong boundary pressure + positive probe
version 2: 15–100
  ↓
version 3: 10–100
```

seed 比較は同一 design-space version 内で行う。

## 2.5 今回特に確認する bound

優先:

- `io_idt_pairs`: initial lower 20 → hard lower 8 を候補
- `center_idt_pairs`: outer_ports で lower 10 張り付きが再現するなら hard lower 5 を候補

ただし hard lower は physical/manufacturing validity を config / constraints で必ず保証する。

---

# Phase 3 — 安全な高速化

## 3.1 Seed-level parallelization

5 cold seeds を outer level で並列化する。

- 1 seed = 1 worker
- worker 内では BLAS thread を原則 1 に固定
- `OMP_NUM_THREADS=1`
- `MKL_NUM_THREADS=1`
- `OPENBLAS_NUM_THREADS=1`

1 / 2 / 4 / 5 workers を benchmark し、最良構成を採用する。

### 必須 parity

serial と parallel で:

- 同一 seed
- 同一 final design-space version
- 同一 primary metrics
- 同一 rank
- 数値差は既定 tolerance 内

を確認する。

## 3.2 I/O

- history flush は best 更新時または一定件数ごとに buffer flush
- checkpoint は budget checkpoint / bound change / best significant improvement 時に保存
- 中断後は latest checkpoint から trajectory continuation または warm-resume 可能にする

## 3.3 Stage 3.2 で後回しにする高速化

- Numba/JIT
- GPU
- COM solver 自体のアルゴリズム置換
- DE 内部の複雑な並列化
- sparse/block-tridiagonal solver への変更

---

# Phase 4 — 小規模テストとデバッグ

本番前に必ず smoke / unit / integration を実施する。

## 4.1 Unit tests

最低限:

1. budget continuation が 500→1000 で population をリセットしない
2. requested budget と actual unique count が一致する
3. adaptive grid が収束しても残 budget を消化する
4. 4000 未収束で 8000 へ auto escalation
5. grid update 時の population re-evaluation が unique design count を増やさない
6. best/median polish metric が分離される
7. soft bound のみ expand 可能
8. hard bound を超えない
9. boundary pressure が 1 seed のみでは発火しない
10. persistent multi-seed pressure で発火する
11. positive boundary probe で expand
12. expansion で design-space version increment
13. expansion で plateau history reset
14. expansion 後 exploration injection が新領域へ入る
15. serial/parallel parity
16. incremental diagnostics aggregation が full evaluation と一致
17. review bundle self-contained test

## 4.2 Synthetic optimizer smoke test

COM を使わない簡単な既知目的関数を用意し、

- optimum が initial bound 外、hard bound 内にあるケース
- optimum が initial bound 内にあるケース
- boundary に見えるが probe で改善しないケース

をテストする。

自動bound拡張ロジックをSAW本番前に検証する。

## 4.3 SAW small smoke test

50 Ω / 1 wiring / 2 seeds / small budgets:

```text
100 → 200 → 400
```

確認:

- continuation
- adaptive grid update
- checkpoint
- bound pressure logging
- bundle generation
- serial/parallel parity

この段階では性能結論を出さない。

## 4.4 Debug exit criteria

- 全 unit/integration tests pass
- no non-finite / unexpected passivity failure
- budget accounting error = 0
- bundle 展開後 test rerun 可
- serial/parallel result parity pass

---

# Phase 5 — 50 Ω 本番実行

## 5.1 Run matrix

wiring:

- outer_ports
- center_outer_same

cold seeds:

- 5 seeds minimum

budget checkpoints:

- 500
- 1000
- 2000
- 4000
- optional 8000 auto escalation

## 5.2 Coordinator behavior

各 global checkpoint で:

1. 全seed状態集約
2. paired convergence metrics 更新
3. boundary pressure 判定
4. 必要なら boundary probe
5. bound expand decision
6. design-space version update
7. converged判定
8. continue / stop / escalate を決定

bound expansion が起きた場合、同一 design-space version で連続2 plateauを得るまで convergence 認定しない。

## 5.3 本番終了条件

各 wiring について以下のどれか:

### A. converged

- 同一 design-space version で連続 2 plateau
- seed dispersion 閾値内
- validation gap 閾値内
- best polish improvement 閾値内
- late improvement なし
- active soft bounds に unresolved strong boundary pressure なし

### B. hard-bound-limited

- hard physical bound に到達
- boundary pressure + positive probe が継続
- これ以上探索空間拡張不可

この場合は `converged` と分けて報告する。

### C. likely_underoptimized

- 8000 でも改善継続
- seed dispersion 大
- late improvements 継続

### D. inconclusive

- numerical instability / insufficient valid candidates 等

---

# Phase 6 — レビューバンドル生成

本番終了後、必ず self-contained review bundle を自動生成する。

例:

```bash
python -m sawopt.reporting.review_bundle \
  --run runs/stage3_2_50ohm \
  --output stage3_2_50ohm_review.zip
```

## 6.1 必須内容

```text
review_bundle/
├─ REVIEW_ME.md
├─ bundle_manifest.json
├─ pyproject.toml
├─ environment/
│  ├─ run_manifest.json
│  ├─ pip_versions.json
│  ├─ git_status.txt
│  └─ git_diff.patch
├─ inputs/
│  ├─ exact_config.yaml
│  └─ exact_com.yaml
├─ source/
│  ├─ sawopt/**/*.py
│  ├─ configs/**              # testsが相対参照する位置にも配置
│  └─ tests/**
├─ results/
│  ├─ convergence_summary.json
│  ├─ convergence_trials.csv
│  ├─ paired_budget_deltas.csv
│  ├─ boundary_events.csv
│  ├─ design_space_versions.json
│  ├─ best_candidates.json
│  ├─ performance_gate.json
│  └─ convergence_report.html
├─ checkpoints/
│  └─ checkpoint_summary.json
└─ tests/
   ├─ pytest.txt or unittest.txt
   ├─ test_summary.json
   ├─ smoke_test.json
   └─ parallel_benchmark.json
```

## 6.2 Bundle integrity

`bundle_manifest.json` に全ファイルの:

- path
- SHA-256
- bytes
- required/optional

を保存する。

source hash が run manifest と一致することを bundle generator 自身が検証する。

## 6.3 Self-contained acceptance

新しい一時directoryへZIPを展開後、bundle内だけで:

1. config読み込み
2. test discovery
3. unit/integration tests
4. manifest/hash verification

が成功するテストを追加する。

---

# Phase 7 — レビュー後の判断

50 Ω benchmark の結果によって次を決定する。

## Case 1: center_outer_same が converged かつ仕様未達

- DMS 1段 + 現行仮COM + 探索可能hard bounds内で仕様達成困難という証拠が強まる。
- hybrid topology / impedance sweepへ進む。

## Case 2: bound expansion で大幅改善

- 旧boundが設計空間を制限していた。
- 新boundを正式 design space とし、再度 convergence 判定。

## Case 3: 8000でもunderoptimized

- optimizer戦略（DE parameters / hybrid global-local / alternative global optimizer）を次段で検討。
- 20–200 Ω本番 sweepは保留。

---

# 最終成果物

Stage 3.2 完了時に最低限以下を提出する。

1. 実装済みsource
2. 全テスト結果
3. small smoke run
4. 50 Ω production run
5. convergence report
6. boundary expansion log
7. parallel benchmark
8. self-contained review bundle ZIP
