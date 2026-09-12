# 非同期本番探索

長時間の本番探索は `sawopt.orchestration` を介して起動します。既存のCOM・Optimizer・同期CLIは変更せず、launcherが短時間で終了した後にworkerが `run-study` を別プロセスで実行します。

## 起動

Codex Hookが保存した `.codex/runtime/current_session.json` を使うため、プロジェクトHookをレビュー・信頼した後に実行します。

production callbackの対象を取り違えないため、可能なら現在のCodex session IDを明示して起動します。明示IDはHookの自動取得値より優先され、manifestへ固定保存されます。

```powershell
python -m sawopt.orchestration.cli launch `
  --config configs/studies/next_50ohm_dms_production.yaml `
  --session-id <CURRENT_CODEX_SESSION_ID> `
  --run-dir runs/async-stage32-production
```

callbackを使わない検証は明示的に無効化できます。

```powershell
python -m sawopt.orchestration.cli launch `
  --config configs/base/b28_dms_baseline.yaml `
  --run-dir runs/async-smoke `
  --no-callback
```

launcherは `run_id`、worker PID、run directoryだけを表示して終了します。本番探索の完了を待ったりログをpollingしたりしません。
非同期launcherの `--resume` は未対応です。既存runのcheckpoint再開は、同期optimizerのcheckpoint interfaceを別途検証してから専用のorchestration interfaceとして追加します。

## 状態確認と復旧

```powershell
python -m sawopt.orchestration.cli status <run_id>
python -m sawopt.orchestration.cli review <run_id>
python -m sawopt.orchestration.cli recover <run_id>
```

各runには `run_manifest.json`（immutable）、`status.json`、`stdout.log`、`stderr.log`、`callback.log` が保存されます。callbackはmanifestに保存されたsession IDを明示して `codex exec resume <SESSION_ID>` を実行し、`--last` は使用しません。callback timeoutはmanifestへ保存された設定（既定30分）で有限化され、timeout後もOptimizer結果は保持されます。

自動callbackは1回だけです。callbackだけが失敗した場合もOptimizerの `COMPLETED`/`FAILED` 結果は保持され、`review` で手動再実行できます。callbackから次のproduction runは起動しません。

## 検証範囲

`status` はoverall state、Optimizer state/exit code、callback state/attempts、worker/optimizer両PIDの生存判定、run directoryを表示します。worker停止時にOptimizer childだけが生きている場合は `ORPHANED_CHILD` として自動再実行を禁止します。

`tests/unit/orchestration/` には、状態遷移・atomic write/stale lock、Windows/Unix detached probe、dummy optimizer成功/失敗、explicit session callback、callback timeout、child orphan検出のテストがあります。本番runはこのリファクタリングの検証では起動しません。
