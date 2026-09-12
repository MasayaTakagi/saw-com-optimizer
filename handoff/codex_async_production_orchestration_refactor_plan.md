# SAW COM Optimizer
# 長時間本番探索の非同期実行・Codex再開機構 リファクタリング作業計画書

作成日: 2026-09-12  
対象: `saw-com-optimizer`  
優先度: High  
実装方針: 段階導入。まず「1本番探索 = 1回の自動resume」まで実装し、完全自律連続探索は行わない。

---

## 1. 目的

本番探索の実行時間が長時間化しているため、CodexエージェントがPython最適化処理の終了を待ち続けたり、定期的にログ・進捗をpollingしたりする運用を廃止する。

目標フローは以下とする。

```text
Codex
  │
  ├─ 実験条件を確定
  ├─ 非同期本番runを登録・起動
  └─ そのターンを終了
          │
          ▼
   [Codexは待機しない]
          │
          ▼
Detached Worker
  │
  ├─ Optimizerを実行
  ├─ 状態・ログ・結果を保存
  └─ 完了/失敗を確定
          │
          ▼
Codex Callback
  │
  ├─ 元のCodex session/threadをresume
  ├─ 結果または失敗ログをレビュー
  ├─ 次実験案を作成
  └─ STOP（次の本番探索は自動開始しない）
```

重要なのは「Codexを一時停止したままPythonが保持する」ことではなく、**Codexのターンを正常に終了させ、Pythonジョブを独立実行し、完了イベント発生時に保存済みsession/threadをresumeする**ことである。

---

## 2. 背景と現在の問題

本番探索では評価回数が増加し、1 runの所要時間が長くなっている。

長時間コマンドをCodexが直接保持すると、以下の問題が生じる。

- Codex側で不要な待機・pollingが発生し得る
- `wait -> status確認 -> wait` のエージェント処理が増える
- 長時間runのログがCodexコンテキストを圧迫する
- Codexセッションと数値計算プロセスのライフサイクルが密結合になる
- Codexを別作業に使いにくい
- terminal/session切断時の責務が曖昧
- 異常終了時の復旧処理が実験スクリプトごとに分散しやすい

このため、AIエージェントと数値計算を明確に分離する。

---

## 3. 設計原則

### 3.1 COM Core / Optimizer CoreはAI非依存とする

以下の層からCodex SDK、Codex CLI、session IDなどへの依存を禁止する。

```text
COM Core
Optimizer Core
Objective / constraints
Search algorithms
Experiment-specific optimization logic
```

Optimizerは「入力を受けて計算し、結果を返す/保存する」責務だけを持つ。

Codex再開処理をOptimizer内の`finally:`等に直接埋め込まないこと。

### 3.2 Orchestration層を独立して設ける

AIとの接続、run状態、detached process、callbackはすべてOrchestration層が担当する。

```text
Codex / Experiment Planner
           │
           ▼
Experiment Orchestrator
           │
           ▼
Optimizer
           │
           ▼
COM Core
```

### 3.3 run単位で状態を永続化する

Pythonプロセスのメモリだけにrun状態を保持しない。

各runディレクトリにmanifest/status/logを保存し、Codexが存在しなくてもrunの状態が判定できるようにする。

### 3.4 callbackは冪等にする

完了通知が重複しても、同一runについてCodex reviewが複数回起動しないこと。

### 3.5 第1段階では完全自律ループを禁止する

今回実装する自動化の上限は以下。

```text
本番探索開始
→ 完了/失敗
→ Codex自動resume
→ レビュー
→ 次実験案提示
→ STOP
```

Codexがレビュー後に次の本番探索を自動起動する機能は実装しない。

---

## 4. 公式Codex機能を利用する前提

2026-09-12時点で、Codex Python SDKはstable releaseとして提供されている。

```bash
pip install openai-codex
```

既存のCodex認証を再利用できる。

Python SDKには保存済みthreadを再開するAPIがある。

```python
with Codex() as codex:
    thread = codex.thread_resume(thread_id, ...)
    result = thread.run("...")
```

CLIにもsession指定resumeが存在する。

```bash
codex exec resume SESSION_ID "follow-up prompt"
```

`--last`依存は禁止する。必ずrunに対応するsession IDを保存し、そのIDを明示指定すること。

Codex Hooksの各command hookには`session_id`がJSON stdinで渡されるため、repo-local hookを使って現在のsession IDを安全に取得できる。

---

## 5. 目標アーキテクチャ

```text
src/sawopt/
├─ com/                       # 既存COM Core
├─ optimization/              # 既存Optimizer Core
│
└─ orchestration/             # NEW
   ├─ __init__.py
   ├─ models.py               # RunManifest / RunStatus
   ├─ run_manager.py          # run生成・状態遷移・lock
   ├─ process_runner.py       # detached worker起動
   ├─ worker.py               # optimizer実行 + callback起動
   ├─ codex_callback.py       # thread resume
   └─ cli.py                  # launch/status/review/recover

.codex/
├─ hooks.json                 # 既存configと衝突しない形で追加
├─ hooks/
│  └─ capture_session.py      # session_id保存
└─ runtime/                   # gitignore
   └─ current_session.json

runs/
└─ <run_id>/
   ├─ run_manifest.json
   ├─ status.json
   ├─ stdout.log
   ├─ stderr.log
   ├─ callback.log
   └─ ...既存の結果ファイル...

tests/
└─ orchestration/
   ├─ test_run_manager.py
   ├─ test_process_runner.py
   ├─ test_worker.py
   └─ test_codex_callback.py
```

注意:

- 上記は論理構成であり、現在のリポジトリ構造を最初に確認してから既存命名規約へ合わせること。
- 既存のリファクタリング済み構造を壊さないこと。
- 実験のたびに`src/sawopt/optimization`へ専用orchestrationコードを追加する構成には戻さないこと。

---

## 6. Run Manifest仕様

最低限、各runに以下を保存する。

```json
{
  "schema_version": 1,
  "run_id": "20260912_153000_xxxxx",
  "experiment_name": "stage34_production",
  "created_at": "2026-09-12T15:30:00+09:00",
  "project_root": "C:/.../saw-com-optimizer",
  "run_dir": "C:/.../runs/...",
  "command": ["python", "-m", "..."],
  "config_path": "...",
  "codex_session_id": "thr_...",
  "codex_model": "...",
  "callback_enabled": true,
  "review_after_completion": true,
  "pid": null
}
```

`status.json`はmanifestから分離する。

例:

```json
{
  "state": "RUNNING",
  "updated_at": "...",
  "worker_pid": 12345,
  "optimizer_pid": 23456,
  "exit_code": null,
  "callback_attempts": 0,
  "callback_completed": false,
  "error": null
}
```

manifestは原則immutable、状態更新は`status.json`へ行う。

atomic writeを使用すること。

例:

```text
status.json.tmp
→ flush/fsync
→ replace status.json
```

途中書き込みによるJSON破損を避ける。

---

## 7. 状態機械

最低限以下を定義する。

```text
CREATED
   ↓
STARTING
   ↓
RUNNING
   ├───────────────┐
   ↓               ↓
COMPLETED         FAILED
   ↓               ↓
CALLBACK_PENDING
   ↓
CALLBACK_RUNNING
   ├───────────────┐
   ↓               ↓
REVIEWED      CALLBACK_FAILED
```

追加可能:

```text
CANCELLED
ORPHANED
```

ただし第1実装で状態を増やしすぎない。

状態遷移は`run_manager.py`の1か所で管理し、任意文字列を各モジュールから直接書き込まない。

---

## 8. Codex session ID取得

### 8.1 repo-local SessionStart hookを使用する

`.codex/hooks.json`から`capture_session.py`を呼ぶ。

hookはstdin JSONから以下を取得する。

```text
session_id
cwd
model
hook_event_name
```

取得結果を

```text
.codex/runtime/current_session.json
```

へatomic writeする。

例:

```json
{
  "session_id": "thr_...",
  "cwd": "C:/.../saw-com-optimizer",
  "model": "...",
  "captured_at": "...",
  "source": "startup"
}
```

### 8.2 stale session対策

非同期run起動時に以下を検証する。

- `current_session.json`が存在する
- cwdが現在のproject rootと一致する
- session取得時刻が極端に古くない
- session IDが空でない

不正なら自動callbackを無効化するか、明示エラーとしてrun開始前に停止する。

**`--last`で代替しないこと。**

別のCodex chatを探索中に開始すると、誤ったsessionをresumeする危険があるため。

---

## 9. 本番run起動フロー

Codexから直接Optimizerを長時間実行しない。

Codexは以下に相当するlauncherだけを実行する。

```bash
python -m sawopt.orchestration.cli launch \
  --config <production-config> \
  --run-dir <run-dir>
```

launcherの責務:

1. current Codex session ID取得
2. run ID生成
3. run directory作成
4. manifest/status作成
5. detached worker起動
6. worker PID保存
7. run ID / PID / run dirを表示
8. 数秒以内に終了

Codexはlauncher成功を確認したら、Optimizer完了をpollingしない。

そのターンでは以下だけをユーザーへ返して終了する。

```text
Production run started asynchronously.
run_id: ...
pid: ...
run_dir: ...
Codex callback: enabled
```

---

## 10. Detached Worker

launcher自身を長時間生存させない。

別プロセスとして`worker.py`をdetached起動する。

```text
Codex shell
   │
   └─ launcher.py
          │
          ├─ manifest作成
          ├─ workerをdetach
          └─ exit
                  │
                  ▼
             worker.py
                  │
                  ├─ optimizer subprocess
                  ├─ exit code取得
                  ├─ status更新
                  └─ Codex callback
```

### Windows優先要件

現在のローカル実行環境を第一対象として、Windowsで親terminal/Codex終了後もworkerが継続することを実機テストする。

実装候補:

- `subprocess.Popen`
- `CREATE_NEW_PROCESS_GROUP`
- 必要に応じて`DETACHED_PROCESS`
- stdinは親terminalから切り離す
- stdout/stderrはrun directoryのファイルへredirect

ただしフラグを決め打ちする前に最小probeを作り、**Codex/terminalを終了しても30～60秒のsleep workerが完走すること**を実機確認する。

platform依存処理は`process_runner.py`へ閉じ込める。

Optimizer本体にWindows固有処理を入れない。

---

## 11. Workerの責務

`worker.py`は以下を実行する。

```python
mark_running()

try:
    exit_code = run_optimizer()
except BaseException:
    record_failure()
    mark_failed()
else:
    if exit_code == 0:
        mark_completed()
    else:
        mark_failed()

if callback_enabled:
    mark_callback_pending()
    run_codex_callback()
```

重要:

OptimizerをPython関数として直接importして実行するよりも、現状のproduction entry pointが安定している場合は、まずsubprocessとして実行して境界を明確にしてよい。

既存production CLI/APIの構造を調査し、最小変更になる方式を選択すること。

---

## 12. Codex callback

### 12.1 Python Codex SDKを第一候補とする

専用モジュール:

```text
src/sawopt/orchestration/codex_callback.py
```

概念実装:

```python
from openai_codex import Codex, Sandbox

def resume_for_review(session_id: str, project_root: str, prompt: str):
    with Codex() as codex:
        thread = codex.thread_resume(
            session_id,
            cwd=project_root,
            sandbox=Sandbox.workspace_write,
        )
        return thread.run(prompt)
```

実際のAPI引数はインストールされているstable SDKのバージョンに合わせて確認すること。

### 12.2 callback prompt

完了時:

```text
The production optimization run has completed.

run_id: <run_id>
run_dir: <absolute path>
status: COMPLETED
exit_code: 0

Review this run now.

Required actions:
1. Read run_manifest.json and status.json.
2. Inspect the generated summary/results/logs.
3. Validate that the run completed correctly.
4. Compare the result with the experiment objective and previous relevant runs.
5. Identify convergence, stability, seed dependence, and any suspicious behavior.
6. Recommend the next experiment or stopping criterion.
7. Do NOT automatically launch another production optimization run.
```

失敗時:

```text
The production optimization run failed.

run_id: <run_id>
run_dir: <absolute path>
status: FAILED
exit_code: <code>

Investigate the failure now.

Required actions:
1. Read run_manifest.json and status.json.
2. Inspect stdout.log and stderr.log.
3. Identify the root cause.
4. Determine whether results are usable.
5. Propose a fix/retry plan if appropriate.
6. Do NOT automatically launch another production optimization run.
```

### 12.3 sandbox

callback reviewには原則:

```python
Sandbox.workspace_write
```

を使用する。

`full_access`をデフォルトにしない。

`--dangerously-bypass-approvals-and-sandbox`等を常用しない。

---

## 13. callback冪等性とlock

同一runについてcallbackを二重起動しない。

以下のいずれか、または組み合わせを実装する。

```text
callback.lock
status.callback_running
status.callback_completed
callback_attempts
```

推奨:

1. callback開始前にatomic lock取得
2. 既に`callback_completed == true`なら何もしない
3. `callback_attempts += 1`
4. `CALLBACK_RUNNING`
5. resume
6. 正常終了なら`REVIEWED`
7. 失敗なら`CALLBACK_FAILED`

自動retryは第1段階では最大1回、または行わない。

無限retryは禁止。

---

## 14. Codex側の運用ルール

`AGENTS.md`または専用ドキュメントに以下を追加する。

### Long-running production run policy

- 本番最適化をCodex shellから同期実行しない
- production runはorchestration launcherを使用する
- launcherがdetached worker起動に成功したらpollingしない
- `stdout.log`を周期監視しない
- completion callbackが元sessionをresumeする
- callback review後に次の本番runを自動開始しない
- ユーザー承認があるまで次のproduction runは開始しない

ただし短時間のunit test、smoke test、数秒～数分の検証処理まで非同期化しない。

---

## 15. CLI

最低限以下を提供する。

```bash
# 非同期本番run開始
python -m sawopt.orchestration.cli launch ...

# 状態確認
python -m sawopt.orchestration.cli status <run_id>

# callbackのみ手動再実行
python -m sawopt.orchestration.cli review <run_id>

# stale RUNNING等を診断
python -m sawopt.orchestration.cli recover <run_id>
```

`status`はAI向けだけではなく、人間がPowerShell等から確認可能な簡潔な出力にする。

例:

```text
run_id: ...
state: RUNNING
worker_pid: ...
optimizer_pid: ...
elapsed: ...
run_dir: ...
callback: pending
```

---

## 16. エラー・復旧設計

最低限以下を考慮する。

### ケースA: Optimizerが非zero exit

- `FAILED`
- exit code保存
- stderr保存
- Codex callback実行

### ケースB: Python exception

- tracebackを`stderr.log`またはstatusへ保存
- `FAILED`
- Codex callback実行

### ケースC: callbackだけ失敗

Optimizer結果は消さない。

```text
COMPLETED
→ CALLBACK_FAILED
```

として保持し、後から

```bash
... review <run_id>
```

で手動resume可能にする。

### ケースD: PC再起動 / worker kill

`RUNNING`のままPIDが存在しない可能性がある。

`recover`で検出し、

```text
ORPHANED
```

または`FAILED`へ遷移できるようにする。

第1段階で自動復旧までは不要だが、誤ってRUNNING扱いし続けないこと。

---

## 17. ログ設計

ログをCodex transcriptへ流し続けない。

run directoryに保存する。

```text
stdout.log
stderr.log
callback.log
```

可能ならOptimizer側の既存ログ形式を維持し、orchestratorが重複ログ基盤を作らない。

callback promptにはログ本文を埋め込まず、run directoryだけ渡す。

Codex自身に必要なファイルを読ませる。

---

## 18. テスト計画

### Phase 0: 現状調査

実装前に必ず実施する。

- 現在のrepo tree確認
- 既存production entry point確認
- run directory生成方法確認
- 現在のlogging/status機構確認
- `.codex/`、`AGENTS.md`、configの既存内容確認
- Codex SDK/CLIバージョン確認
- 既存テスト実行

この調査結果に基づき、下記ファイル名/配置を必要最小限修正してよい。

### Phase 1: session capture

テスト:

- SessionStart hookでsession IDが保存される
- resume時にも更新される
- JSONがatomicに更新される
- project rootが一致する

### Phase 2: detached process

最小probeを作成する。

```text
worker starts
→ launcher exits
→ Codex/terminalから制御が戻る
→ worker sleeps 30-60 sec
→ marker file作成
```

親terminalが終了してもmarkerが生成されることを確認する。

### Phase 3: orchestration state

Optimizerの代わりに短いdummy commandを実行する。

成功ケース:

```text
CREATED
→ STARTING
→ RUNNING
→ COMPLETED
→ CALLBACK_PENDING
```

失敗ケース:

```text
CREATED
→ STARTING
→ RUNNING
→ FAILED
→ CALLBACK_PENDING
```

### Phase 4: callback mock

Codex SDKをmockし、

- 正しいsession IDが使われる
- `--last`相当の処理をしていない
- callback重複が防止される
- callback失敗時にOptimizer結果が保持される

ことを確認する。

### Phase 5: real Codex callback smoke test

本物のCodexを使った短時間runを1回だけ実行。

例:

```text
dummy optimizer
→ 30 sec sleep
→ result.json作成
→ 元session resume
→ Codexがresult.jsonを読む
```

この段階では本番SAW探索を使わない。

### Phase 6: SAW short-run integration

評価回数を小さくした既存Optimizerでend-to-end検証。

### Phase 7: production

実際の長時間runへ適用。

---

## 19. 受入条件

以下をすべて満たしたら完了とする。

### Architecture

- [ ] COM CoreにCodex依存がない
- [ ] Optimizer CoreにCodex依存がない
- [ ] Codex callbackはorchestration層だけに存在する
- [ ] experiment固有コードをoptimization coreへ不要に増やしていない

### Async execution

- [ ] launcherが短時間で終了する
- [ ] launcher終了後もworker/Optimizerが継続する
- [ ] Codexが本番runをpollingする必要がない
- [ ] stdout/stderrがrun directoryへ保存される

### Session safety

- [ ] session IDがrun manifestへ保存される
- [ ] `--last`を使用しない
- [ ] 別Codex sessionを開いても元runのresume先が変わらない
- [ ] stale/missing session IDを検出できる

### State/recovery

- [ ] 成功時にCOMPLETEDへ遷移する
- [ ] 失敗時にFAILEDへ遷移する
- [ ] callbackの状態が追跡できる
- [ ] callback二重実行を防止できる
- [ ] callbackだけ手動再実行できる

### Safety

- [ ] callbackが次のproduction runを自動起動しない
- [ ] auto-run無限ループが存在しない
- [ ] sandbox bypassをデフォルト使用しない
- [ ] 既存の本番探索結果と計算ロジックを変更していない

### Regression

- [ ] 既存unit testsが通る
- [ ] 既存Optimizerの同期実行経路が必要なら維持される
- [ ] 数値結果がorchestration導入前後で一致する

---

## 20. 実装優先順位

### P0: 必須

1. 現状調査
2. session ID capture
3. run manifest/status
4. detached worker
5. Optimizer subprocess実行
6. completion/failure判定
7. Codex SDK `thread_resume`
8. callback idempotency
9. dummy integration test
10. short SAW run test
11. documentation

### P1: 次段階

- stale process検出改善
- manual recover
- callback retry policy
- 複数run同時実行時の排他/制御
- human-readable run list

### P2: 今回は実装しない

- Codexがレビュー後に自動で次runを開始
- 無人で何世代も探索
- scheduler/queue cluster化
- Web UI
- DB導入
- Redis/Celery等の外部queue
- cloud migration

現時点ではfilesystemベースで十分。

---

## 21. 実装時の禁止事項

以下は行わないこと。

1. Optimizer Coreから直接Codexをimportする
2. 各実験scriptへcallbackコードをコピペする
3. `codex exec resume --last`に依存する
4. stdout全量をcallback promptへ埋め込む
5. callback失敗をOptimizer失敗として扱う
6. callbackから無制限に次runを開始する
7. detached確認なしにWindows process flagsを決め打ちする
8. 既存COM/Optimizerの数値ロジックをこのリファクタリングと同時に変更する
9. 不要な大規模フレームワークを導入する
10. 現在のrepo構造を確認せず上記サンプルtreeをそのまま機械的に作る

---

## 22. Codexへの作業指示

この計画に従ってリファクタリングを実施すること。

最初にコードを変更せず、以下を確認する。

1. repo tree
2. production runの現在のentry point
3. Optimizer Coreと実験wrapperの境界
4. run/output/logの現在の保存方法
5. `.codex`および`AGENTS.md`
6. 現在インストールされているCodex CLI / Python SDK
7. Windows上の現在のPython起動方法
8. 既存テスト

その後、既存設計を最大限再利用する**最小差分の具体的実装計画**を短く提示し、そのまま実装へ進むこと。

実装中は以下を守ること。

- COM/Optimizerの数値アルゴリズムを変更しない
- orchestrationだけを追加/整理する
- detached動作はdummy workerで先に実証する
- session IDは明示保存する
- real Codex callback testはdummy runで先に行う
- 最後に短時間SAW runでend-to-end testする
- 本番長時間探索を勝手に開始しない

作業終了時には以下を報告すること。

```text
1. 変更したファイル一覧
2. 最終アーキテクチャ
3. session ID取得方法
4. detached実行方法
5. callback resume方法
6. 状態遷移
7. 実施したテストと結果
8. 既存Optimizerへの影響
9. 未解決リスク
10. 実際にproduction runを開始するコマンド例
```

---

## 23. 完了後の理想運用

人間/Codex:

```text
「この条件で本番探索を開始」
```

Codex:

```text
設定確認
↓
async launcher起動
↓
run_idを報告
↓
ターン終了
```

数時間後:

```text
Optimizer完了
↓
workerがstatus更新
↓
元Codex sessionをresume
```

Codex:

```text
結果ファイルを読む
↓
収束性・seed依存・目的関数・制約をレビュー
↓
次実験案を提示
↓
STOP
```

この状態を今回のリファクタリングの最終目標とする。

---

## 24. 参考となる公式仕様

実装時には最新のstable APIを再確認すること。

- Codex SDK  
  https://developers.openai.com/codex/sdk
- Codex Python SDK API Reference  
  https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md
- Codex CLI / Developer commands  
  https://developers.openai.com/codex/cli/reference
- Codex Hooks  
  https://developers.openai.com/codex/hooks

