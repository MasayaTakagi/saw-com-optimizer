# 非同期本番探索

長時間の本番探索は `sawopt.orchestration` を介して起動します。既存のCOM・Optimizer・同期CLIは変更せず、launcherが短時間で終了した後にworkerが `run-study` を別プロセスで実行します。

## 起動

新しいC2C管理下の非同期作業では、元のDesktop threadを起動前に確定し、queue continuationとして起動します。`--thread-id` はその正確なthread ID、C2C task ID、PLAN iteration、完了後に続ける `NEXT_EXPECTED_STEP` と組にして渡します。実行前にqueue preflightを通し、manifestに固定されたthreadへ一度だけ通知します。

```powershell
python -m sawopt.orchestration.cli launch `
  --config configs/studies/dms_topology_screening.yaml `
  --continuation-mode queue `
  --thread-id <EXACT_ORIGINAL_DESKTOP_THREAD_ID> `
  --c2c-task-id <C2C_TASK_ID> `
  --plan-iteration <PLAN_ITERATION> `
  --next-expected-step "verify the run and continue the accepted task" `
  --run-dir runs/async-dms-topology-screening
```

queue modeではschema-v3 manifestの `continuation_mode`、`original_thread_id`、
`queue_preflight.status=PASS`、`review_after_completion=true` を検証します。
このmodeでは旧callbackを無効にするため `callback_enabled=false` となり、
`codex_session_id` は不要です。session IDとthread IDは異なる識別子です。

既存manifestの再接続や、明示的に選択した歴史的な `legacy_resume` runでは、
保存済みCodex sessionを使うcallbackを維持します。Hookが保存した
`.codex/runtime/current_session.json` を利用でき、明示的な `--session-id` は
Hookの自動取得値より優先されmanifestに保存されます。

callback/continuationを使わないローカル検証では明示的にdisabledにできます。次の例は
`legacy_resume` callbackを使うproduction launchではなく、完了後の継続を無効にした検証です。

```powershell
python -m sawopt.orchestration.cli launch `
  --config configs/base/b28_dms_baseline.yaml `
  --run-dir runs/async-smoke `
  --no-callback
```

launcherは `run_id`、worker PID、run directoryだけを表示して終了します。本番探索の完了を待ったりログをpollingしたりしません。
既存runへの `launch --resume --run-dir <既存run>` は実装済みです。`STARTING` / `RUNNING` でworkerまたはoptimizerのPIDが生存していれば、そのrunへ再接続し、`session_checkpoint.json` と `status.json` の再接続情報を更新します。これらの状態で対象プロセスが残っていなければ `ORPHANED` に遷移してから、既存run/checkpointを使ったdetached resumeを開始します。`FAILED`、`ORPHANED`、`ORPHANED_CHILD` からも既存runを再開できます。それ以外の状態では再開を拒否します。これはoptimizer runの再接続・復旧であり、C2C PLANやChatGPT会話を再開・再送する機能ではありません。

## 状態確認と復旧

```powershell
python -m sawopt.orchestration.cli status <run_id>
python -m sawopt.orchestration.cli review <run_id>
python -m sawopt.orchestration.cli recover <run_id>
```

各runには `run_manifest.json`（immutable）、`status.json`、`stdout.log`、`stderr.log` が保存されます。`legacy_resume` runは `callback.log` を持ち、callbackはmanifestに保存されたsession IDを明示して `codex exec resume <SESSION_ID>` を実行し、`--last` は使用しません。callback timeoutはmanifestへ保存された設定（既定30分）で有限化され、timeout後もOptimizer結果は保持されます。queue modeの送信状態とattempt数は `status.json` と `continuation_delivery.json` で確認します。

`legacy_resume` callbackは保存済みsessionに対して1回だけ実行されます。callbackだけが失敗した場合もOptimizerの `COMPLETED`/`FAILED` 結果は保持され、`review` で手動再実行できます。callbackから次のproduction runは起動しません。queue modeではworkerが完了後に固定済みthreadへ1回だけ `codex queue` を送り、delivery ledgerでattemptとreceiptを管理します。失敗またはacknowledgement不明時に自動再送せず、既存runのdurable evidenceを使って同じC2C taskから復旧します。

## 完了後のCodex継続

Queue modeではdetached jobの完了後に公式CLIの
`codex queue --thread <開始前に取得した元Desktop thread ID> --message <完了参照>`
を1回だけ呼び、元のDesktop threadへ戻る方式を標準にします。スレッドIDを
推測・後から探索せず、`--last` や新規threadを使いません。キューはメッセージを
既存threadへ順序づけて届ける手段であり、optimizer checkpointの復元やthreadの
writer ownership取得は行いません。運用条件、重複防止、Windows profile確認、失敗時の
手動復旧は [`../c2c/OPERATIONS.md`](../c2c/OPERATIONS.md) を参照してください。

キューに含めるのは `TASK_ID`、`RUN_ID`、完了済みrun/resultの正確な参照、
`NEXT_EXPECTED_STEP`、one-shot claimで生成された `DELIVERY_ID`、delivery sentinelなど、
元の計画と実行結果を結び付ける最小情報です。receiverは `DELIVERY_ID` がdurableなclaimと
一致することをtask/run/sentinel/threadと合わせて検証してからreceiptを確定します。
元のPLANを貼り直さず、到着したturnで同じthreadとrunの完了・結果・重複有無を確認し、
既存のC2C PLAN/HANDOFFにある `NEXT_EXPECTED_STEP` から作業を続けます。キューが失敗・
不確定なときは自動再送やjob再実行をせず、結果を保持して同じ `TASK_ID` のまま手動復旧します。

既存の `legacy_resume` manifestはmanifestに固定された `codex_session_id` を指定して
`codex exec resume <session-id>` を実行します。`legacy_resume` callbackはlockと有限timeoutで
保護され、自動実行は1回です。失敗時はoptimizer結果を保持し、`review` による手動確認・再実行を
使います。新しいqueue-mode manifestはschema-v3でthread/task/PLAN/送信preflightを固定し、
completion後の通知にはone-shot delivery claimと同一threadでのreceiver validationを要求します。
これらのmodeを既存run上で切り替えたり、履歴runをqueue-modeへ読み替えたりしません。

productionの復帰時は既存のrun artifactを根拠にします。`run_manifest.json` はimmutableな
run/continuation binding、`status.json` はrunとcallback/queue deliveryの状態・結果、
`session_checkpoint.json` はlaunch/reattach/resumeの記録、optimizer checkpoint/resultは
存在する場合に計算状態を保持します。完了通知はこれらを参照し、会話本文だけを計算完了の
証拠にしません。callbackやqueued continuationは次のproduction runを起動しません。

## 検証範囲

`status` はoverall state、Optimizer state/exit code、callback state/attempts、worker/optimizer両PIDの生存判定、run directoryを表示します。worker停止時にOptimizer childだけが生きている場合は `ORPHANED_CHILD` として自動再実行を禁止します。

`tests/unit/orchestration/` には、状態遷移・atomic write/stale lock、Windows/Unix detached probe、dummy optimizer成功/失敗、explicit session callback、callback timeout、child orphan検出のテストがあります。本番runはこのリファクタリングの検証では起動しません。
