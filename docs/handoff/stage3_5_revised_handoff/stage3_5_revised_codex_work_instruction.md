# Codex作業指示書 — Stage 3.5 corrective restart

## 目的

途中runで判明したStage 3.5実装上の問題を修正し、Phase Aを再生成した後、Phase Cを同一source/config hashで完全再実行する。

canonical root:

`C:\Users\sub\Documents\ChatGPT\saw-com-optimizer`

---

## 0. 作業前preflight

1. `AGENTS.md`を読む。
2. `git rev-parse --show-toplevel`
3. `git status --short`
4. `git branch --show-current`
5. `git rev-parse HEAD`
6. unrelated user changesを保持する。
7. 既存途中runを削除しない。historical evidenceとして保持する。

---

## 1. 添付patchをレビューして適用

対象patch:

`stage3_5_corrective_patch.diff`

適用前:

`git apply --check <path-to-patch>`

問題なければ:

`git apply <path-to-patch>`

patchがcurrent HEADと軽微にずれている場合は、意味を維持して手動適用してよい。

### Patchの必須意図

#### A. config normalization

`run_stage35()`はraw `load_experiment_config()`だけで開始せず、canonical continuation/optimizer A/Bと同じ`normalize_convergence_config()`を通す。

目的: `layout`等のhistorical/default fields欠落を防止。

YAMLへ`layout`を局所的にベタ書きして回避しない。

#### B. certificate fail-closed

`grid_converged`等がrecordにない場合にoptimistic defaultを与えない。

missing evidenceはPhase Dで:

`inconclusive_missing_evidence`

にする。

#### C. local sensitivity false-positive修正

hard bound外の未評価perturbationを`outside improvement`としない。

#### D. late evidence

S1設計は128k/192k/256kのlate recordsを使う。

#### E. cross-version parity

historical 256k final designをhistorical `validation_frequencies_hz`上でcurrent sourceにより再評価し、全seed PASSしない限りPhase Aを通過させない。

---

## 2. Patch適用後tests

最低限:

- patched unit tests
- study/reporting targeted tests
- full test suite

例:

`python -m pytest tests/unit/studies/test_search_efficiency.py tests/unit/reporting/test_search_space_diagnostics.py`

その後full regression。

### 必須確認

- `run_stage35`のnormalized configに`layout`が存在する
- S1 hard bounds unchanged
- `io_idt_pairs` lower 8
- missing certificate evidenceがPASSにならない
- late checkpoint extraction = 128k/192k/256k
- parity gate fail-closed

---

## 3. Phase A-R再実行

exact Stage 3.4b bundleを使用する。

生成物:

- `search_space_diagnostics.md`
- `search_space_diagnostics.json`
- `search_space_elites.csv`
- `local_sensitivity.csv`
- `pairwise_diagnostics.csv`
- `cross_version_parity.csv`
- `search_space_s1.yaml`
- `search_space_s1_rationale.md`

### Gate

`cross_version_parity_pass = true`

かつ全8 seed `parity_pass = true`。

FAILならPhase Cを開始しない。

### S1確認

途中結果で得られた`center_idt_pairs [5,24]`と同じになるとは限らない。

修正版diagnosticsから再生成されたS1をsource of truthとする。

---

## 4. S1 freeze

- hard bounds unchanged
- no frozen variable
- hash保存
- Phase C開始後は変更禁止

旧S1 artifactを新runへ暗黙流用しない。

---

## 5. Phase C-R完全再実行

**旧A-armを再利用しない。**

A/B/C/Dをすべてnew run directoryでcold-start。

固定:

Seeds = 20260917–20260920
Budgets = 16k, 32k, 64k

run開始前にmanifestへ:

- Git HEAD
- source hash
- merged config hash
- S1 hash
- normalized layout/config provenance

を保存。

4 armが同じsource/config lineageであることを確認する。

---

## 6. Phase C結果判定

既存promotion rulesに従う。

単なるscalar objectiveだけで決めない。

必須比較:

- validated median primary
- worst seed
- target reach count
- median evals to target
- duplicate rate
- boundary events
- recovery events
- validation stability

winnerが明確でなければ`INCONCLUSIVE`で止める。

Phase Dを無理に実行しない。

---

## 7. Phase D実行条件

promotion candidateがexactly oneの場合のみ実行。

fresh seeds = 20260921–20260928

最大256k。

### L-SHADEがcandidateの場合

Stage 3.4b相当certificate fieldsをL-SHADE recordが実際に生成していることを事前確認する。

patchのfail-closedによって`inconclusive_missing_evidence`になる場合は、evidence生成をcanonical reusable implementationとして追加し、testsを追加する。

**値をdefaultで埋めてcertificateを通してはいけない。**

---

## 8. Windows subprocess console問題

Optimizer worker起動時に不要なconsole windowが出る問題が再現する場合は、Phase C長時間run前に修正してよい。

ただしoptimization semanticsを変えないこと。

変更時はprocess_runner unit testを追加/更新する。

---

## 9. Stop conditions

以下で停止してreview bundleを作る。

- parity gate failure
- full regression failure
- source/config/S1 hash drift
- cold-start violation
- budget accounting mismatch
- validation semantics mismatch
- certificate evidence不足が解消できない
- bundle hash failure

---

## 10. 最終提出物

1. 修正内容summary
2. tests結果
3. cross-version parity結果
4. 修正版Phase A outputs
5. frozen S1 + hash
6. Phase C 4-arm結果
7. promotion decision
8. Phase Dを実行した場合はcertificate結果
9. git diff/status/HEAD
10. self-contained review bundle

review bundle推奨名:

`stage3_5_search_space_optimizer_efficiency_corrected_review.zip`

---

## 11. 禁止事項

- 旧A-armの再利用
- Stage 3.4b 512k延長
- impedance sweep開始
- certificate閾値緩和
- missing evidenceの偽PASS
- historical best vector warm-start
- COM/spec変更
- force push/history rewrite

