# SAW COM Optimizer
# 非同期Orchestration 今後の作業計画

作成日: 2026-09-12  
対象: 現在実装中の async orchestration / Codex callback 機構  
方針: 現在の設計を維持し、P0の実運用ブロッカーを先に除去する。  
重要: P0完了までは長時間production探索を開始しない。

---

## 1. 現在地

現時点では、以下が確認済み。

- pytest: 139 passed
- unittest discovery: 101 tests, OK
- orchestration単体テスト: 13 passed
- detached dummy probe: 成功
- `maxiter=1` の短時間SAW runをworker経由で実行: 成功
- COM / Optimizer数値コードの変更なし
- Codex callbackはPython SDKではなく利用可能なCodex CLIを使用
- `--last`には依存せず、session IDを明示してresumeする設計
- COM Core / Optimizer CoreとCodex依存の分離は概ね達成

一方で、production運用前に以下が未完了。

1. 実Windows環境でのHook発火確認
2. callbackによる「元のCodex sessionへの実resume」のE2E確認
3. 複数Codex session使用時のsession ID取り違え防止
4. stale lock / orphan process / resume semantics等の耐障害性改善

---

# 2. 作業の優先順位

## P0: Production投入前に必須

### P0-1. Windows Hookを実環境で確実に動作させる

目的:
`SessionStart` hookから現在のCodex session IDを確実に取得する。

実施内容:

1. 現在の`.codex/hooks.json`を確認
2. Windowsで安全に実行できるcommandへ修正
3. shell substitutionや複雑なquote依存を避ける
4. 必要なら薄い`.cmd` / `.ps1` wrapperを使用
5. Hook trust設定を完了
6. Codex sessionを新規開始
7. `.codex/runtime/current_session.json`の生成を確認
8. 以下を検証
   - `session_id`が空でない
   - `cwd`がproject root
   - timestampが現在時刻付近
   - source/eventがSessionStart由来

受入条件:

- [ ] Windows上で実SessionStart時に毎回ファイルが生成/更新される
- [ ] hookの失敗が見逃されない
- [ ] Codex session IDが実際の現在sessionと一致する
- [ ] hook commandにUnix shell前提の構文がない

---

### P0-2. session IDの取り違えを防ぐ

現状リスク:

```text
Session A starts
→ current_session.json = A

Session B starts
→ current_session.json = B

Session Aからproduction launch
→ Bをmanifestへ保存する可能性
```

これはproduction運用上の重大な問題。

推奨設計:

**production launch時にはsession IDを明示的に固定する。**

優先順位:

#### 第一候補
Codexがlauncherへ明示指定する。

```bash
python -m sawopt.orchestration.cli launch \
  --session-id <CURRENT_CODEX_SESSION_ID> \
  ...
```

Hookは現在session IDをCodexに伝えるための補助機構として使う。

#### 第二候補
Hookの`additionalContext`等を利用し、Codex自身へ

```text
Current Codex session ID: ...
For async production launch, pass this ID explicitly.
```

を注入する。

#### fallback
`current_session.json`を使用する場合でも、

- session freshness
- cwd
- source
- explicit confirmation

を検証する。

ただしproductionでは明示`--session-id`を優先する。

受入条件:

- [ ] launcherが`--session-id`を受け取れる
- [ ] explicit IDがmanifestへ固定される
- [ ] `current_session.json`よりexplicit IDが優先される
- [ ] 2つのCodex sessionを同じrepoで開いても取り違えない
- [ ] `--last`を使用しない

---

### P0-3. Real Codex callback E2E smoke test

本番SAW runではなくdummy runで実施する。

テストフロー:

```text
Codex Session A
   ↓
Hook発火
   ↓
session_id=Aを取得
   ↓
async dummy run launch
   ↓
launcher終了
   ↓
Codexターン終了
   ↓
workerだけ継続
   ↓
30～60秒sleep
   ↓
result.json生成
   ↓
codex exec resume A
   ↓
Session Aが再開
   ↓
Codexがresult.jsonを読む
   ↓
status=REVIEWED
```

callback promptには以下を含める。

```text
This is an async callback smoke test.

Read:
- run_manifest.json
- status.json
- result.json

Report:
1. run_id
2. result value
3. whether this session appears to be the original resumed session

Do not start another run.
```

確認項目:

- [ ] launcherは数秒以内に終了
- [ ] workerは親Codex/terminalから独立して継続
- [ ] result.json生成
- [ ] callback.log生成
- [ ] 正しいsession IDで`codex exec resume`実行
- [ ] 元のCodex sessionが再開
- [ ] Codexがresult.jsonを実際に読む
- [ ] callback終了後`REVIEWED`
- [ ] 新しいproduction runを自動起動しない
- [ ] callback重複なし

### Production Gate A

P0-1～P0-3がすべて成功した場合のみ、

> 「単一runの非同期execution + 元Codex sessionへのcallback」

をproduction利用可能と判定する。

---

# 3. P1: Production前後で強化すべき耐障害性

P0を通過後、最初の本番長時間runの前に可能な限り対応する。

---

## P1-1. `.status.lock`のstale lock対策

現在の単純lock file方式では、process crashやPC shutdown後にlockが残る可能性がある。

改善案:

lock fileに最低限以下を保存。

```json
{
  "pid": 12345,
  "created_at": "...",
  "hostname": "..."
}
```

lock取得時:

1. lock fileが存在しない → 取得
2. 存在する
3. PID生存確認
4. 生存している → 正常に待機
5. PID不存在かつ一定時間以上古い → stale lockとして回収
6. atomicに新lock取得

受入条件:

- [ ] process kill後に永久lockしない
- [ ] `recover`自身がstale lockで止まらない
- [ ] 同時writeの排他は維持

---

## P1-2. worker / optimizer両PIDの生存判定

現在はworker PID中心の判定。

改善:

```text
worker_pid
optimizer_pid
```

の両方を確認する。

分類例:

```text
worker alive / optimizer alive
→ RUNNING

worker dead / optimizer alive
→ INCONSISTENT or ORPHANED_CHILD
→ 自動再実行禁止

worker dead / optimizer dead
→ ORPHANED or FAILED候補
```

重要:
optimizerが生きている状態で同一runを再実行しない。

受入条件:

- [ ] worker死亡/optimizer生存を検出可能
- [ ] 二重production runを防げる
- [ ] status CLIでPID状態が確認できる

---

## P1-3. `--resume` semanticsを整理

現状は既存run directory拒否と`--resume`が矛盾する可能性がある。

今回は無理に複雑なresume orchestrationを作らない。

推奨:

### Phase 1
async launcherから`--resume`を一旦非公開または明示的にunsupportedにする。

### Phase 2
必要性が出た段階で専用interfaceを設計。

例:

```bash
python -m sawopt.orchestration.cli resume-run <run_id>
```

既存optimizer checkpoint semanticsを調査し、orchestration stateとの整合を取る。

受入条件:

- [ ] CLIに存在するオプションが実際に機能する
- [ ] 「存在するrun directoryだから起動前に失敗」という矛盾がない

---

## P1-4. callback timeout

Codex CLIが何らかの理由で終了しない場合、worker全体が永続的にcallback中にならないようにする。

例:

```text
callback_timeout_minutes = 30
```

timeout時:

```text
CALLBACK_FAILED
reason = timeout
```

Optimizer resultは保持。

手動再実行:

```bash
python -m sawopt.orchestration.cli review <run_id>
```

受入条件:

- [ ] callbackに有限timeoutがある
- [ ] timeoutでもOptimizer結果を失わない
- [ ] manual review可能

---

## P1-5. 人間向けstatus表示改善

`REVIEWED`だけではOptimizer成功/失敗が分かりにくい。

例:

```text
run_id: ...
overall_state: REVIEWED

optimizer:
  state: FAILED
  exit_code: 3

callback:
  state: COMPLETED
  attempts: 1

worker_pid: ...
optimizer_pid: ...
run_dir: ...
```

成功run:

```text
optimizer.state: COMPLETED
callback.state: COMPLETED
overall_state: REVIEWED
```

受入条件:

- [ ] Optimizer成否とcallback成否を区別できる
- [ ] exit codeを表示
- [ ] run directoryを表示
- [ ] PID状態を表示

---

# 4. P1完了後の統合試験

## Integration Test 1: Success

```text
short SAW run
→ COMPLETED
→ callback
→ REVIEWED
```

確認:

- 数値結果が従来同期runと一致
- callbackがresult summaryを読む
- 次runを勝手に開始しない

---

## Integration Test 2: Optimizer failure

意図的にinvalid config等で失敗。

```text
RUNNING
→ FAILED
→ CALLBACK_PENDING
→ callback
→ REVIEWED
```

Codexはstderrを読み、失敗原因を報告する。

確認:

- callback成功によりOptimizer failureが隠れない
- status CLIでは`optimizer: FAILED`が見える

---

## Integration Test 3: callback failure

Codex executableを一時的に見つからない状態にする等でcallbackだけ失敗させる。

```text
COMPLETED
→ CALLBACK_FAILED
```

その後:

```bash
... review <run_id>
```

でmanual recovery。

確認:

- Optimizer結果は保持
- 二重callbackなし

---

## Integration Test 4: multi-session

同じrepoで

```text
Codex A
Codex B
```

を起動。

Aからrun A
Bからrun B

を開始。

確認:

```text
run A → session A
run B → session B
```

と正しく固定される。

これは今回のsession設計の最重要回帰テスト。

---

# 5. Production Gate B

以下を満たした場合、長時間production探索へ適用可能と判定する。

## 必須

- [ ] Windows Hook実動作
- [ ] explicit session ID固定
- [ ] real callback smoke成功
- [ ] multi-session test成功
- [ ] stale lock対策
- [ ] optimizer child process生存判定
- [ ] callback timeout
- [ ] failure path test成功
- [ ] manual callback retry成功
- [ ] 既存全test pass
- [ ] COM / Optimizer数値結果不変

---

# 6. 最初のProduction Runの進め方

いきなり最大探索量を使わない。

## Step 1: medium run

現在の本番設定より短い中規模runで確認。

目的:

- 数十分程度のdetach
- Codex session解放
- callback
- review

を実環境で確認する。

## Step 2: 実production

medium runが問題なければ、本番条件へ。

Codexはrun開始後:

```text
run_id
worker_pid
run_dir
callback enabled
```

だけ報告してターンを終了する。

**進捗pollingは禁止。**

ユーザーが明示的に進捗確認を要求した場合のみ`status` CLIを利用する。

---

# 7. 今回は実装しないもの

以下は次フェーズ。

- callback後の自動次run投入
- 完全自律的な複数世代探索
- 複数GPU/複数machine scheduler
- DB / Redis / Celery
- Web UI
- 実験queue manager
- 自動budget管理
- 自動停止条件のAI判断によるrun再投入

まずは

```text
1 run
→ async execution
→ 1 callback
→ human review / approval
```

を安定させる。

---

# 8. Codexへの具体的作業指示

以下の順番で作業すること。

## Stage 1
Windows Hookを実環境で修正・確認する。

コード変更前後で以下を報告:

- 現在のhook command
- 問題点
- 修正後command
- 実発火結果
- captured session ID

## Stage 2
launcherにexplicit `--session-id`を追加し、manifestへ固定する。

優先順位:

```text
explicit --session-id
> validated hook-derived session ID
> callback disabled / error
```

曖昧な状態でproduction callbackを有効化しない。

## Stage 3
real Codex callback dummy smoke testを行う。

本番SAW runは禁止。

成功条件をすべて確認して報告する。

## Stage 4
multi-session testを行う。

A/Bの2sessionを作り、run先が混ざらないことを確認。

## Stage 5
P1耐障害性を実装。

順序:

1. stale lock
2. worker/optimizer PID
3. callback timeout
4. status表示
5. resume semantics整理

## Stage 6
全test suiteを実行。

最低限:

```text
pytest
unittest discovery
orchestration tests
detached dummy probe
real callback smoke
multi-session test
short SAW integration
failure path tests
```

## Stage 7
最終レビュー資料を作成。

以下を含めること。

```text
1. 変更ファイル一覧
2. final architecture
3. Hook実装
4. session ID固定方法
5. detached process方式
6. callback方式
7. lock/recovery方式
8. test結果
9. production readiness判定
10. 残存リスク
11. production launchコマンド例
```

---

# 9. 停止条件

以下のいずれかが起きた場合は、本番探索を開始せずユーザーへ報告する。

- HookがWindowsで安定して発火しない
- session IDの正当性を保証できない
- callbackが別sessionへresumeする
- detached workerが親terminal終了後に死ぬ
- worker/optimizer二重実行の可能性が残る
- callback失敗でOptimizer結果が失われる
- COM / Optimizer数値結果に差分が出る
- 既存testが回帰する

---

# 10. 最終目標

```text
Codex Session A
   │
   ├─ 実験条件確定
   ├─ 自分のsession IDを明示してlaunch
   └─ ターン終了
           │
           ▼
      worker only
           │
           ├─ 長時間Optimizer
           ├─ logs/results保存
           └─ status更新
           │
           ▼
      Codex resume A
           │
           ├─ 結果レビュー
           ├─ 次実験案
           └─ STOP
```

この状態を、非同期Orchestration第1フェーズの完成条件とする。
