# SAW COM Optimizer
# Async Orchestration Production Gate A 作業指示書

作成日: 2026-09-12  
対象: 現在実装済みの async orchestration / Codex callback 機構  
目的: Production Gate Aを安全に通過させる  
重要: この作業中に実production探索を開始してはならない。

---

## 1. 現在の状態

確認済み:

- pytest: 151 passed
- unittest: 112 tests OK
- orchestration tests: 24 passed
- detached worker: 成功
- 短時間SAW runをworker経由で実行: 成功
- COM / Optimizer数値コード: 変更なし
- production run: 未起動

未完了:

- 実Codex SessionStart Hookのtrust / 実発火確認
- real `codex exec resume <session_id>` E2E
- real multi-session A/B test
- Windows PID livenessの安全化確認
- callback先が本当に要求session/threadと一致することの実検証

---

# 2. この作業で明示的に許可する操作

このProduction Gate A検証に限り、以下の操作を許可する。

1. このrepo内の `.codex/runtime/` へのsession情報の書き込み
2. dummy test用run directoryへのファイル作成・更新
3. SessionStart Hookの実行とtrust確認
4. 現在session IDの取得・保存・検証
5. `codex exec resume <session_id>` の実行
6. resumeに必要なOpenAI/Codexサービスへの通信
7. dummy callback smoke test
8. real multi-session test
9. テストに必要な一時ファイルの生成・削除

禁止:

- 実production探索の開始
- 本番用大規模SAW最適化の開始
- `--dangerously-bypass-approvals-and-sandbox` 等による承認機構の無効化
- sandbox / approvalの恒久的無効化
- callback後の次production run自動開始
- COM Core / Optimizer Coreの数値アルゴリズム変更
- 無関係なリファクタリング

権限不足が発生した場合は、承認機構を回避せず、
**必要な操作・対象ファイル・外部通信先の種類を明示して承認を求めること。**

---

# 3. 最優先: Windows PID livenessを安全化

## 問題

Windows上で以下のUnix流の生存確認を使ってはならない。

```python
os.kill(pid, 0)
```

Windowsでは安全な「存在確認」にならない可能性がある。

## 作業

repo内を検索し、PID liveness判定の実装をすべて列挙する。

例:

```text
process_runner.pid_exists
run_manager._pid_exists
その他
```

重複実装があればplatform-safeな共通関数へ統合する。

推奨:

- Windows:
  - Win32 APIを`ctypes`経由で利用
  - `OpenProcess`
  - `WaitForSingleObject`
  - `CloseHandle`
- POSIX:
  - `os.kill(pid, 0)`でよい

新規依存`psutil`は、既に依存している場合のみ利用可。
この修正だけのために必須依存として追加しないこと。

## 必須実機probe

Windows上で:

```text
dummy process start
→ sleep 60 sec
→ pid_exists(pid)を複数回実行
→ dummy processが終了していないことを確認
→ 60 sec後に自然終了
→ pid_exists(pid) == False
```

さらに:

```text
status CLIを複数回実行
→ worker / optimizerが停止しない
```

を確認する。

受入条件:

- [ ] WindowsでPID確認が対象processを終了させない
- [ ] POSIX互換性を壊していない
- [ ] PID判定実装が可能な限り一元化
- [ ] probeの結果を記録

---

# 4. callback lockのstale recovery確認・修正

以下の状態を再現する。

```text
optimizer COMPLETED
→ callback.lock作成
→ callback開始前にworker crash
```

この状態から:

```bash
python -m sawopt.orchestration.cli review <run_id>
```

が復旧できることを確認する。

必要であれば `.status.lock` と同じstale lock処理を共通化する。

受入条件:

- [ ] stale callback.lockで永久にreview不能にならない
- [ ] lockの二重取得防止は維持
- [ ] callback二重実行は起きない

---

# 5. Windows SessionStart Hookを実環境で確認

## hooks.json

Windows commandは可能な限りquote-freeにする。

例:

```json
"commandWindows": ".codex\\hooks\\capture_session.cmd"
```

shell substitution:

```text
$(...)
```

は禁止。

## capture_session

Hook payloadの実値を保存する。

推奨:

```json
{
  "session_id": "...",
  "session_cwd": "...",
  "project_root": "...",
  "model": "...",
  "captured_at": "...",
  "hook_event_name": "SessionStart"
}
```

`session_cwd`を保存前にproject rootへ上書きしないこと。

検証:

```text
session_cwd == project_root
OR
session_cwd is under project_root
```

## additionalContext

可能ならSessionStart Hookの応答で、Codex自身へ現在session IDを通知する。

趣旨:

```text
Current Codex session ID: <ID>.
When launching an async production run,
pass this exact ID explicitly using --session-id.
```

`current_session.json`はfallback用途とする。

## 実試験

synthetic stdinだけでなく、
**実Codex session開始 → Hook runner → wrapper → capture script**
の経路を通す。

確認:

- Hookがtrust済み
- `.codex/runtime/current_session.json`生成
- session_idが空でない
- session_cwd正しい
- current session IDと一致
- Hook失敗がsilent successになっていない

受入条件:

- [ ] real SessionStart Hook成功
- [ ] session ID取得成功
- [ ] cwd検証が実値に対して機能
- [ ] Codex自身が自分のsession IDを保持できる

---

# 6. launcherのsession ID固定

production callback用sessionは明示指定を最優先する。

優先順位:

```text
explicit --session-id
    >
validated hook-derived ID
    >
callback disabled / launch error
```

曖昧なsession IDでcallbackを有効にしないこと。

manifestに以下を保存:

```json
{
  "codex_session_id": "...",
  "codex_session_source": "explicit"
}
```

またはfallback時:

```json
{
  "codex_session_id": "...",
  "codex_session_source": "hook"
}
```

受入条件:

- [ ] explicit IDが最優先
- [ ] manifestへ固定
- [ ] launch後に別sessionが開始してもrunのresume先が変わらない
- [ ] `--last`不使用

---

# 7. callbackのresume先検証を強化

単なるexit code 0のみで`REVIEWED`にしない。

可能であればCodex CLIのstructured/json出力を利用し、

```text
requested session/thread ID
==
actual resumed thread/session ID
```

を確認する。

一致しない場合:

```text
CALLBACK_FAILED
reason = resumed thread ID mismatch
```

とする。

structured outputからthread/session IDを取得できない場合は、
利用中のCodex CLIバージョンで可能な最も強い方法を調査し、
検証方法を報告すること。

受入条件:

- [ ] exit codeだけに依存しない、または依存せざるを得ない理由を明記
- [ ] 別threadを新規生成した場合に成功扱いしない設計を優先

---

# 8. Real Codex callback dummy E2E smoke test

実production SAW runは禁止。

## テスト内容

```text
Session A
  ↓
real SessionStart Hook
  ↓
session_id=A
  ↓
dummy async launch --session-id A
  ↓
launcher終了
  ↓
workerだけ継続
  ↓
30～60秒sleep
  ↓
result.json生成
  ↓
callback
  ↓
codex exec resume A
  ↓
元Session Aでレビュー
  ↓
REVIEWED
```

dummy `result.json`例:

```json
{
  "smoke_test": true,
  "value": 12345,
  "message": "async callback smoke test completed"
}
```

callback prompt:

```text
This is an async orchestration smoke test.

Read:
- run_manifest.json
- status.json
- result.json

Report:
1. run_id
2. result value
3. requested Codex session ID
4. whether the callback resumed the intended session

Do not launch another run.
Do not modify COM or Optimizer code.
```

## 必須確認

- [ ] launcherが数秒以内に終了
- [ ] workerが継続
- [ ] Codex側で待機/pollingしない
- [ ] result.json生成
- [ ] callback.log生成
- [ ] `codex exec resume A`
- [ ] Aが実際に再開
- [ ] callbackがresult.jsonを読む
- [ ] status最終状態`REVIEWED`
- [ ] callback重複なし
- [ ] 次run自動起動なし

---

# 9. Real multi-session test

同じrepoでSession A / Session Bを用意する。

テスト:

```text
Session A
→ run A launch --session-id A

Session B
→ run B launch --session-id B
```

それぞれdummy resultを生成してcallback。

期待:

```text
run A → Session A
run B → Session B
```

確認:

- [ ] manifest AにA
- [ ] manifest BにB
- [ ] current_session.jsonが途中で上書きされてもmanifestは不変
- [ ] callback AはAへ
- [ ] callback BはBへ
- [ ] cross-resumeなし

---

# 10. failure-path smoke

少なくとも1回、callbackのみ失敗させる。

例:

- fake/unavailable Codex executable
- intentional timeout

期待:

```text
optimizer/dummy result = COMPLETED
callback = CALLBACK_FAILED
result remains intact
```

その後:

```bash
python -m sawopt.orchestration.cli review <run_id>
```

でmanual retry成功を確認。

受入条件:

- [ ] callback失敗で結果を失わない
- [ ] manual retry可能
- [ ] callback二重実行なし

---

# 11. 全テスト

変更完了後に最低限実行:

```text
pytest
unittest discovery
orchestration tests
Windows PID liveness probe
detached dummy probe
real SessionStart Hook
real callback E2E smoke
real multi-session test
callback failure/retry
short SAW integration
```

COM / Optimizerの数値コードに差分がないことも再確認。

---

# 12. Production Gate A判定

以下をすべて満たした場合のみ`PASS`。

- [ ] Windows-safe PID liveness
- [ ] stale callback lock recovery
- [ ] real SessionStart Hook
- [ ] explicit session ID固定
- [ ] real `codex exec resume` E2E
- [ ] intended session/threadへのresume確認
- [ ] real multi-session A/B成功
- [ ] callback failure/manual retry成功
- [ ] 全test pass
- [ ] COM / Optimizer数値コード不変
- [ ] production run未起動

1つでも未達なら:

```text
Production Gate A: FAIL / NOT READY
```

と明記する。

---

# 13. 最終報告形式

作業終了時に以下を報告すること。

## A. 変更ファイル

```text
path
purpose
```

## B. 修正内容

1. PID liveness
2. callback lock
3. Hook
4. session ID固定
5. resume先検証
6. callback failure recovery

## C. 実検証結果

```text
pytest:
unittest:
orchestration:
PID probe:
real Hook:
real callback:
multi-session:
failure/retry:
short SAW:
```

## D. Production Gate A

```text
PASS
```

または

```text
FAIL
```

## E. 未解決事項

残っているリスクを列挙。

## F. 次の推奨

Gate A PASSなら、
productionではなくまずmedium-duration SAW runを推奨すること。

---

# 14. 最重要制約

この作業中は、実production runを絶対に開始しない。

この作業の最終目的は、

```text
1 run
→ detached
→ Codex解放
→ completion
→ original Codex session resume
→ review
→ STOP
```

を実環境で証明することである。
