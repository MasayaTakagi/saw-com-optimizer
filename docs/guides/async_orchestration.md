# 非同期本番探索

30分以上かかる見込みの探索は、`sawopt.orchestration` を介して起動します。
既存のCOM・Optimizer・同期CLIを直接長時間実行せず、launcherがmanifestを
保存した後にworkerが別プロセスで探索を実行します。

> **重要:** Stage 4Bで使われた dedicated legacy `codex exec resume`
> callback は新規productionの標準経路ではありません。次の長時間production
> runを開始する前に、exact original threadを使うqueue-native continuationと
> GitHub review-evidence exportをactive orchestration branchへ統合し、短い
> harmless runで再qualificationする必要があります。

## 起動前

本番runでは、対象config、実装、budget、seed、checkpoint方針、出力先、
review-evidence contract、preflightをGitHub上で確認できるbranch/commitに
保存します。外部reviewの手順は
[`github_review_workflow.md`](github_review_workflow.md)、post-run evidenceの
標準は [`postrun_review_contract.md`](postrun_review_contract.md) を参照して
ください。run自体はユーザーが明示的に承認した後に開始します。

production continuationの対象を取り違えないため、新規runではdetach前に
**exact original Codex thread ID** を取得しmanifestへ固定します。session ID
とthread IDは別のidentityであり、queue targetへsession IDを代用しません。

新規productionではtarget contractとして:

```text
continuation_mode = queue
original_thread_id = <exact thread id>
```

を使用します。

legacy `codex exec resume` 用のsession metadataはhistorical manifestの読み取り
互換・既存run recoveryのために残してよいですが、新規production launchで
選択してはいけません。

## 起動

queue-native実装のCLI形状はactive implementationでqualificationしたものを
使用します。概念上必要な情報は以下です。

```powershell
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli launch `
  --config <PRODUCTION_CONFIG> `
  --continuation-mode queue `
  --thread-id <EXACT_ORIGINAL_THREAD_ID> `
  --run-dir <RUN_DIR>
```

実際の引数が追加のdelivery metadataを必要とする場合は、qualification済み
CLI contractに従います。

callback/continuationを無効にするrunは、そのrunに対する明示的な判断がある
場合だけdisabled/no-callback相当を使います。

launcherは `run_id`、worker PID、run directory、continuation modeを表示して
終了します。detached worker開始後に `stdout.log` をpollしたり、完了まで
foregroundで待機したりしません。

起動直後に `run_manifest.json` を確認し、少なくとも:

- exact production source SHA;
- config/protocol identity;
- output path;
- `continuation_mode: queue`;
- exact `original_thread_id`;
- durable one-shot delivery metadata;
- post-run review destination/contract;

がlaunch authorizationと一致することを確認します。

identityや設定が指定と異なる場合は、そのlaunchを有効なproductionとして
扱わず、別runを自動で起動しません。

## 状態確認と復旧

`status` / `recover` / `resume` 等はactive implementationのqualified contractを
使用します。

既存runの数値checkpoint recoveryと、完了後のCodex continuationは別概念です。

- **optimizer resume:** 同じrun directory/checkpointから数値探索を復旧する。
- **thread continuation:** 完了状態を元のCodex threadへ通知し、evidence publisher
  を再開する。

完了済みqueue-native runを「session resume」として再launchし、同じ計算を
再実行してはいけません。

one-shot queue deliveryが曖昧になった場合はfail closedとし、証拠なしに同じ
messageを再送しません。

## Post-run continuation

新規productionでの標準flow:

```text
optimizer COMPLETED / FAILED
→ durable completion evidence
→ one-shot queue claim
→ codex queue --thread <original-thread-id> --message <bounded handoff>
→ same original thread continuation
→ lightweight review evidence export
→ commit / push
→ REVIEW_WAITING
→ STOP
```

sender側のexit 0だけでsame-thread deliveryを証明したことにはしません。
receiver evidenceを取得できる場合はexact thread/delivery identityを確認します。

continuationされたCodexの仕事はreview evidenceのpublisherです。外部review前に:

- topology/designの最終promotion;
- `current_baseline.md` の科学判断更新;
- roadmap gateの完了扱い;
- 次のproduction run開始;
- PR merge;

を自動実行しません。

## 結果レビュー用GitHub evidence

新規runの標準destination:

```text
reports/experiment_reviews/<stage>/<run_id>/
```

同じexperiment branchへcommit/pushします。

Stage 4Bで使用した
`reports/stage4b_production_review/...` はhistorical evidenceとしてそのまま
保持し、新規規約に合わせるためだけの移動は行いません。

review packageにはsummary/manifest/config/protocol/integrity/terminal cell
results/convergence/boundary/runtime/limitations等の軽量evidenceを含め、巨大な
checkpoint、population dump、cache、raw dense array、full stdout/stderr、
callback/Codex rollout logは原則commitしません。

詳細な必須構造、hash、size、redaction、completeness gateは
[`postrun_review_contract.md`](postrun_review_contract.md) に従います。

## Review state semantics

数値runの完了とscientific reviewを分離します。

Codex continuationが正常終了しただけでrunを `REVIEWED` と呼びません。
外部review待ちの正常なhandoffは:

```text
REVIEW_WAITING
```

とします。

external ChatGPT review後のscientific dispositionはGitHub上のcloseout、
experiment register、baseline update等で記録します。

## Legacy compatibility

既存のhistorical runには:

- `codex_session_id`;
- legacy callback state;
- `callback.log`;
- `codex exec resume` provenance;

が残る場合があります。これらの履歴を破壊しません。

ただし新規production runではlegacy resumeを選択しないことをpolicy gateと
します。active implementationがまだlegacy-onlyの場合、新しい長時間runを
開始するのではなく、先にorchestration migrationを完了させます。

## Stage 4C precondition

Stage 4Cのlong-running productionを開始する前に、最低限:

1. queue-native exact-thread continuationがactive branchへ統合済み;
2. C2C-only metadataへの必須依存が除去済み;
3. legacy resumeが新規productionから禁止済み;
4. generic review exporterがcanonical review directoryを生成可能;
5. one-shot delivery/completeness/redaction/size gateのtestsがPASS;
6. harmless short runで
   `completion → queue → original thread → export → push → REVIEW_WAITING`
   のE2EがPASS;

であることを確認します。

このqualificationはStage 4Cのscientific productionとは別タスクです。
