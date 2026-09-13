# SAW Optimizer
# Luna → Sol オンデマンド・エスカレーション パイロット導入指示書

## 1. 目的

SAW optimizer開発において、Codexの通常作業をGPT-5.6 Lunaで実行しつつ、設計判断・実験条件判断・異常解析など高い推論能力が必要な場面のみGPT-5.6 Solへエスカレーションする。

目的は以下の両立である。

- Luna単独運用で発生する判断ミス・手戻りを減らす
- 全作業をSolで実行する場合より上位モデル使用量を抑える
- 長時間実験のやり直しを減らす
- ChatモードのSolによる最終レビュー工程は維持する

本導入はまだ標準運用ではない。

最初は、

```text
Stage 1
Luna → Sol Escalation Pilot
```

として1つの実作業で検証する。

---

# 2. 基本アーキテクチャ

採用する構成は以下。

```text
ChatGPT 5.6 Sol
    │
    │ 実験計画・作業指示
    ▼
Codex GPT-5.6 Luna root
    │
    ├─ 通常実装
    ├─ テスト
    ├─ ログ解析
    ├─ ドキュメント作成
    ├─ 実験実行
    │
    └─ 高リスク判断を検出
              │
              ▼
       GPT-5.6 Sol subagent
       判断・レビューのみ
              │
              ▼
        Lunaへ回答返却
              │
              ▼
        Lunaが作業再開
              │
              ▼
          結果レポート
              │
              ▼
ChatGPT 5.6 Sol
最終レビュー・次計画
```

---

# 3. 基本原則

## 3.1 Lunaをrootとする

通常のCodex作業はGPT-5.6 Lunaをroot agentとして実施する。

Lunaは以下を担当する。

- コード読解
- 実装
- テスト追加
- テスト実行
- 実験スクリプト実行
- ログ確認
- 結果整理
- README / report更新
- 明確な仕様に基づく修正
- Sol回答の実装への反映

---

## 3.2 Solは判断専用とする

Solは原則として、

```text
reviewer / decision agent
```

として使用する。

Solへ通常の実装作業を丸投げしない。

原則としてSol自身はソースコードを直接変更しない。

Solの役割は、

```text
判断
原因分析
設計レビュー
選択肢比較
実験条件レビュー
```

までとする。

実際の変更はLunaが行う。

---

# 4. Multi-Agent設定

現在正常に動作している環境を優先する。

既にLuna rootからSolを明示指定してspawn可能である場合、

```text
multi_agent_v2
```

などへ不用意に移行しない。

特に、

```toml
[features.multi_agent_v2]
```

等の設定を、このパイロットのためだけに追加してはならない。

現在利用可能な、

```text
spawn_agent
wait_agent
send_input
close_agent
```

等の既存インターフェースを使用する。

---

# 5. Sol呼び出し方式

Solを呼び出す場合は原則、

```text
model = gpt-5.6-sol
fork_context = false
```

を使用する。

利用可能な場合のみreasoning effortを指定してよい。

推奨:

```text
reasoning_effort = high
```

非常に重大な判断に限り、それ以上を検討してよい。

ただし内部reasoning量は外部から確認できないため、

```text
requested reasoning effort
```

と

```text
verified backend behavior
```

を区別して記録すること。

---

# 6. Escalation Packet

Solへ親セッション全体を渡すことを原則禁止する。

Lunaが必要情報を整理し、

```text
Escalation Packet
```

を作成して渡す。

フォーマットは以下。

```text
# Escalation Packet

## Task
現在行っている作業。

## Goal
今回達成したい目的。

## Current State
現在の実装・実験状況。

## Decision Required
Solに判断してほしい一点。

## Why Escalation Is Required
なぜLunaだけで確定すべきでないか。

## Options
候補A:
候補B:
候補C:

必要な場合のみ列挙する。

## Constraints
変更してはいけない条件。

## Evidence
関連するログ、数値、テスト結果、
既存実験結果など。

## Risk
誤った判断をした場合の影響。

## Requested Output
1. 推奨案
2. 理由
3. 反対案を採用しない理由
4. 必要な追加検証
5. 実装時の注意点
```

長大なコードをそのまま添付しない。

必要な箇所だけ抜粋する。

---

# 7. 強制Solエスカレーション条件

以下に該当した場合、Luna単独で変更を確定してはならない。

Solへエスカレーションする。

## 7.1 Optimizer

以下を変更する場合。

```text
optimizer algorithm
```

例:

- Legacy-DE
- L-SHADE
- その他探索アルゴリズム
- hybrid方式
- optimizer切替条件

---

## 7.2 Objective / Constraint

以下を変更する場合。

- objective function
- penalty
- constraint
- weighting
- feasibility判定
- ranking方法
- multi-objective統合方法

---

## 7.3 Search Space

以下を変更する場合。

- パラメータ上限
- パラメータ下限
- topology
- parameter grouping
- center / outer等の拘束関係
- 固定パラメータの解除
- 新規設計変数の追加

---

## 7.4 Convergence

以下を変更する場合。

- convergence判定
- stagnation判定
- early stopping
- evaluation budget
- restart条件
- population schedule
- seed数

---

## 7.5 COM / Physics

以下を変更する場合。

- COM core
- 数式
- 行列計算
- boundary condition
- couplingモデル
- acoustic/electricalモデル
- impedance処理
- S parameter生成方法

物理モデルに影響する変更は必ずエスカレーションする。

---

# 8. 実験結果に関する強制エスカレーション

以下の場合もSolに相談する。

## 8.1 過去結果との逆転

例:

```text
以前:
Legacy-DE > L-SHADE

今回:
L-SHADE > Legacy-DE
```

のように、重要な傾向が逆転した場合。

単純に新結果を正しいものとして扱わず、

```text
実験条件差
実装差
探索budget
seed
search space
収束状態
統計ばらつき
```

を含めSolへレビューさせる。

---

## 8.2 想定外の大幅改善・悪化

objectiveや特性が突然大幅に変化した場合。

特に、

```text
コード変更量に対して結果変化が大きすぎる
```

場合は必ず確認する。

---

## 8.3 長時間再実験

変更によって数時間以上の実験を再実行する必要がある場合、

実行前にSolへ、

```text
本当に再実験が必要か
実験条件は十分か
より安価な確認方法がないか
```

をレビューさせる。

---

## 8.4 公平性への影響

比較実験で、

- budget
- seed
- initial population
- stopping condition
- constraints
- preprocessing

などの公平性に影響する変更を行う場合。

---

# 9. 一般的なエスカレーション条件

SAW固有条件に加え、以下もSol対象とする。

- 作業指示書に複数の合理的解釈がある
- 仕様と既存コードが矛盾する
- 仕様と既存テストが矛盾する
- 複数の実装方針から選択する必要がある
- root causeが不明
- 同じ問題への修正が2回失敗した
- architecture変更が必要
- public interfaceを変更する
- backward compatibilityに影響する
- データ破損・過去結果無効化の可能性がある

---

# 10. Solへエスカレーションしない作業

以下は原則Lunaだけで処理する。

- logging追加
- CSV出力
- JSON出力
- plot作成
- Markdown report
- README
- CLI option追加
- typo
- formatting
- import整理
- 単純な関数分割
- 明確な仕様通りのコード実装
- 既存仕様に対するテスト追加
- ファイル移動
- archive整理
- 実験結果の定型集計

Solを使うこと自体を目的にしてはならない。

---

# 11. Over-Escalation防止

Lunaは、

```text
難しそうだから
```

だけを理由にSolを呼んではならない。

必ず、

```text
どの判断が必要なのか
```

を明文化できる場合のみ呼び出す。

悪い例:

```text
コードが複雑なのでレビューしてください。
```

良い例:

```text
population縮小率を変更すると、
Stage 3.4bとの比較公平性が崩れる可能性がある。
既存方式維持と変更のどちらを採用すべきか判断してほしい。
```

---

# 12. Sol出力フォーマット

可能ならSolへ以下の形式で回答させる。

```text
## Recommendation

採用すべき案。

## Confidence

High / Medium / Low

## Reasoning Summary

判断理由。

## Rejected Alternatives

採用しなかった案と理由。

## Required Validation

追加確認が必要なら記載。

## Implementation Constraints

Lunaが実装するときに守る条件。

## Stop Condition

この判断だけでは進めるべきでない場合は明記。
```

---

# 13. Lunaによる判断の利用

Sol回答を受け取っても、Lunaは無条件で実装してはならない。

以下を確認する。

```text
Sol回答が作業指示書と矛盾していない
Sol回答が既存仕様と矛盾していない
Sol回答が対象問題に答えている
必要な追加検証が示されていないか
```

矛盾がある場合は、

```text
send_input
```

等で同じSol agentへ追加質問できる場合、まず追加確認する。

同一問題で無制限に新しいSol agentを作らない。

---

# 14. Sol使用数

Stage 1ではSol subagentは、

```text
同時最大1 agent
```

とする。

通常は1判断につき1 agent。

同じ問題に対して複数Sol agentを並列生成しない。

必要であれば同一agentへ追加質問する。

---

# 15. Spawn失敗時

Sol spawnに失敗した場合、無制限に設定を変更してはならない。

最大3回まで原因確認する。

確認対象:

```text
model指定
spawn schema
Codex version
利用可能モデル
現在のruntime
config
```

3回で解決しなければ、

```text
SOL_ESCALATION_UNAVAILABLE
```

として記録する。

その判断が重大でなければLunaで続行可能。

重大な判断なら作業を止め、

```text
Human / Chat Sol review required
```

として結果報告する。

---

# 16. モデル実体の記録

現在のruntimeでは、requested modelと実際のbackend identityを独立確認できない場合がある。

そのためログでは、

```text
Requested model:
gpt-5.6-sol

Requested reasoning:
high

Observed backend model:
not independently verified
```

のように区別する。

確認不能なものを、

```text
確認済み
```

と記述してはならない。

---

# 17. Escalation Log

今回のパイロットでは全Sol呼び出しを記録する。

例:

```text
reports/escalation_log.md
```

フォーマット:

```text
# Escalation 001

## Timestamp

## Trigger
なぜSolを呼んだか。

## Category
Optimizer / Search Space / Convergence / COM / Experiment / Other

## Question
Solへの質問。

## Requested model
gpt-5.6-sol

## Requested reasoning
high

## fork_context
false

## Sol recommendation

## Luna action
採用 / 一部採用 / 不採用

## Implementation

## Verification

## Outcome
Successful / Failed / Pending

## Was escalation necessary?
Yes / Probably / No
```

---

# 18. Missed Escalation Log

最終レビュー時に、

```text
本来Solへ相談すべきだったが、
Lunaが単独で判断した
```

ケースが判明したら記録する。

```text
missed_escalations
```

として集計する。

---

# 19. パイロット評価指標

今回のStage 1では最低限以下を測る。

```text
Sol spawn数
自動Sol spawn数
人間指示によるSol spawn数
不要だったSol spawn数
missed escalation数
Sol判断採用数
Sol判断不採用数
spawn failure数
再実装回数
再実験回数
テスト失敗回数
```

可能なら、

```text
Lunaのみで作業した部分
Sol判断を使用した部分
```

も区別する。

---

# 20. 重要な比較指標

パイロット終了時に以下を評価する。

## Quality

Solを使うことで、

```text
Luna単独より明らかな判断ミスが減ったか
```

---

## Efficiency

Solを呼ぶことで、

```text
無駄なやり直し
再実装
再実験
```

が減ったか。

---

## Escalation Precision

```text
本当に必要な場面だけSolを使えたか
```

---

## Escalation Recall

```text
必要な判断をLunaが見逃さなかったか
```

---

# 21. Stage 1では行わないこと

今回は以下を行わない。

- 全Codex作業への即時標準化
- Terraとの比較
- Sol root方式への変更
- multi_agent_v2への移行
- 複数Sol agentによるensemble
- Solによる大量コード実装
- 完全自動化された長時間実験判断
- 人間レビューの廃止
- Chat Sol最終レビューの廃止

---

# 22. 最終レポート

作業完了時、

```text
reports/luna_sol_pilot_review.md
```

を作成する。

以下を含める。

```text
# Luna → Sol Pilot Review

## 1. Task Summary

## 2. Luna Work Summary

## 3. Sol Escalations

## 4. Escalation Statistics

Sol calls:
Automatic:
Manual:
Unnecessary:
Missed:

## 5. Important Decisions

## 6. Implementation Results

## 7. Test Results

## 8. Experiment Results

## 9. Failures / Rework

## 10. Efficiency Assessment

## 11. Quality Assessment

## 12. Problems with Escalation Mechanism

## 13. Recommendation
```

Recommendationは以下から選択する。

```text
A. ADOPT
B. ADOPT WITH CHANGES
C. CONTINUE PILOT
D. REJECT
```

---

# 23. Chat Solレビュー用サマリー

レポート冒頭に以下を必ず付ける。

| Metric | Result |
|---|---|
| Sol calls | |
| Automatic escalations | |
| Manual escalations | |
| Unnecessary escalations | |
| Missed escalations | |
| Sol decisions adopted | |
| Sol decisions rejected | |
| Spawn failures | |
| Rework caused by Luna error | |
| Re-experiments caused by implementation error | |

その下に、

```text
Overall pilot assessment:
```

を1〜3文で記載する。

---

# 24. AGENTS.mdへの追加

既存AGENTS.mdを破壊せず、適切な位置に以下の趣旨を追加する。

```text
## Sol Escalation Policy

You are the Luna root implementation agent.

Perform routine implementation, tests, experiment execution,
logging, reporting, and clearly specified changes yourself.

Use GPT-5.6 Sol only for bounded high-risk judgment tasks.

You MUST escalate before changing:

- optimizer algorithms
- objective functions
- penalties or constraints
- search-space definitions
- convergence or early-stopping logic
- evaluation budgets when comparison fairness may change
- COM/physics calculations
- experiment conditions affecting comparison validity
- architectural interfaces
- behavior that could invalidate previous experiment results

You MUST also escalate when:

- current results materially contradict previous results
- there are multiple reasonable interpretations of the specification
- root cause is unclear and a design change is being considered
- two repair attempts for the same issue have failed
- a long-running experiment would need to be repeated because of a proposed change

Do NOT escalate routine implementation,
tests, logging, plotting, documentation,
formatting, simple refactoring,
or changes whose behavior is fully specified.

When escalating:

1. Create a self-contained Escalation Packet.
2. Prefer fork_context=false.
3. Explicitly request gpt-5.6-sol.
4. Use one Sol agent at a time.
5. Ask Sol for judgment/review, not full implementation.
6. Resume implementation yourself after receiving the decision.
7. Record the escalation and outcome.

Never claim that the backend model identity
or actual internal reasoning effort was verified
unless the runtime explicitly exposes that information.
```

文章は既存AGENTS.mdの書式に合わせて調整してよい。

意味は変更しない。

---

# 25. 導入時の禁止事項

以下は禁止する。

```text
動作しているCodex設定を理由なく変更する

multi_agent_v2を試験目的だけで有効化する

Solを通常workerとして乱用する

長い会話履歴を毎回Solへforkする

Solへコードベース全体を無条件で読ませる

判断理由を記録せずSolをspawnする

同じ問題へ多数のSol agentを生成する

Sol回答を検証せずそのまま実装する
```

---

# 26. パイロット完了条件

以下を満たしたらStage 1完了とする。

1. 実際のSAW optimizer作業を1件完了
2. Lunaをrootとして使用
3. 必要な場合のみSolを使用
4. escalation logを保存
5. テストを実行
6. 必要な実験を完了
7. 結果レポートを作成
8. ChatGPT Solによる外部レビュー用成果物を作成

---

# 27. 今回の最重要評価点

このパイロットで最も確認したいのは、

```text
Solを呼べるか
```

ではない。

既にその基本機能は確認済みである。

確認するのは、

```text
Lunaが適切なタイミングだけSolへ相談することで、

Luna単独より判断ミスと手戻りを減らしつつ、

Solを常用するより効率的に開発を進められるか
```

である。

したがって、

```text
Sol呼び出し回数が多い
```

こと自体を成功とは評価しない。

理想は、

```text
通常作業の大部分 = Luna
重要な分岐判断のみ = Sol
最終品質確認 = Chat Sol
```

である。

---

# 28. 作業開始指示

以上のポリシーを現在のSAW optimizerプロジェクトへパイロット導入する。

まず現在のAGENTS.mdおよびCodex設定を確認する。

既存の動作を壊さない範囲で必要最小限の変更だけを行う。

設定・ポリシー導入後、その時点で指定されている次の実作業を、

```text
Luna root → Sol on-demand escalation
```

方式で実施する。

作業完了後は追加の本番作業へ自動的に進まず、

```text
reports/luna_sol_pilot_review.md
```

および関連ログをまとめて停止する。

その成果物をChatGPT 5.6 Solによるレビューへ渡せる状態にすること。