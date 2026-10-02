# 非同期本番探索

30分以上かかる見込みの探索は、`sawopt.orchestration` を介して起動し
ます。既存のCOM・Optimizer・同期CLIを直接長時間実行せず、launcherが
manifestを保存した後にworkerが別プロセスで探索を実行します。

## 起動前

本番runでは、対象config、実装、budget、seed、checkpoint方針、出力先、
preflightをGitHub上で確認できるbranch/commitに保存します。外部reviewの
手順は [`github_review_workflow.md`](github_review_workflow.md) を参照して
ください。run自体はユーザーが明示的に承認した後に開始します。

production callbackの対象を取り違えないため、run開始前に有効なCodex
session IDを取得します。明示IDはHookの自動取得値より優先され、manifest
に固定保存されます。`--last` は使用しません。

## 起動

```powershell
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli launch `
  --config configs/studies/dms_topology_screening.yaml `
  --session-id <CURRENT_CODEX_SESSION_ID> `
  --run-dir runs/async-dms-topology-screening
```

session fileを使う場合は `--session-file` を指定します。callbackを使わ
ないrunは、そのrunに対する明示的な判断がある場合だけ `--no-callback`
を指定します。launcherは `run_id`、worker PID、run directoryを表示して
終了します。detached workerの開始後に `stdout.log` をpollしたり、完了を
待ったりしません。

起動直後に `run_manifest.json` を確認します。本番callbackを有効にした
runでは、`codex_session_id` が非null、`callback_enabled: true`、
`review_after_completion: true` であることを確認します。manifestの
identityや設定が指定と異なる場合は、そのlaunchを有効なものとして扱わ
ず、次のproduction runを起動しません。

## 状態確認と復旧

```powershell
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli status <run_id>
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli review <run_id>
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli recover <run_id>
```

各runにはimmutableな `run_manifest.json`、`status.json`、
`stdout.log`、`stderr.log`、`callback.log` が保存されます。callbackは
manifestに固定されたsession IDを使って `codex exec resume <SESSION_ID>`
を実行します。timeoutは有限です。

既存runを再接続または復旧するときは、同じrun directoryを指定した
`launch --resume` を使います。既存のcheckpoint/resultを使い、同じ計算を
新規launchとして置き換えません。workerとoptimizerの状態に応じて再接続、
`ORPHANED` 判定、既存checkpointからのresumeを行います。

自動callbackは1回だけです。callbackが失敗してもOptimizerの
`COMPLETED` / `FAILED` 結果は保持し、`review` から結果を確認します。
完了通知は結果の確認を促すもので、optimizer recoveryや次のproduction
runの承認ではありません。callbackから次のproduction runを起動しません。

## 結果レビュー

run完了後、軽量なsummary、manifest metadata、結果表、decision evidence、
provenanceをGitHub上のcloseout branch/PRに記録します。raw checkpointsや
巨大run artifactは無理にGitHubへ保存せず、必要な場合は既存のdata-
management方針に従い、review bundleをユーザー経由で共有します。

## 検証範囲

`status` はoverall state、Optimizer state/exit code、callback state/attempts、
worker/optimizer PID、生存状態、run directoryを表示します。worker停止時
にOptimizer childだけが生きている場合は `ORPHANED_CHILD` として自動再実行
を禁止します。

`tests/unit/orchestration/` には状態遷移、atomic write/stale lock、detached
process検出、dummy optimizer成功/失敗、explicit session callback、callback
timeout、child orphan検出のfocused testsがあります。
