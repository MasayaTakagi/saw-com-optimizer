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

新規manifestはschema v4です。continuationの既定値は`queue`で、明示的な
`--no-callback`は`disabled`として記録します。`legacy_resume`は過去manifestの
読み取り・復旧に限り、新規launchでは拒否されます。queue modeでは
`CODEX_THREAD_ID`が必須で、任意の`--thread-id`はその値と一致しなければなりません。
`--session-id`と`--session-file`はqueue routingに使用できません。

新規のuser-authorizedまたはranking-eligible productionでは、raw runの保存先に
absoluteな外部persistent root/pathを明示します。通常は既存の保存rootを
`--run-root`で渡し、run IDをその直下に作成します。既存の`--run-dir`を使う場合も
absolute pathが必要です。どちらも全登録worktree、`.git`、review publication path、
Windows reparse point、保存先の一意性、parentの書き込み可否を検査します。
Git worktree検出やpath検査に失敗した場合はlaunchを止め、repository `runs/`へ
fallbackしません。manifestには`external_persistent_v1`と保存root、repository root、
launch元worktreeを記録します。historical manifestではこれらのoptional fieldが
なくても読み取りを継続します。

launch例:

```powershell
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli launch `
  --config <PRODUCTION_CONFIG> `
  --thread-id <EXACT_ORIGINAL_THREAD_ID> `
  --review-stage <STAGE> `
  --review-spec <FROZEN_SPEC_ID> `
  --run-root <ABSOLUTE_PERSISTENT_RUN_ROOT>
```

launch時に保存先の外部性と一意性を確認したうえで、Codex実行ファイル/version/helpの
preflightを行い、有限queue timeoutとfrozen review specをmanifestへ保存します。
preflightが失敗した場合はrun directoryを作成せず停止します。raw orchestration/
optimizer outputは外部persistent rootに置きます。軽量review packageは引き続き
`reports/experiment_reviews/<stage>/<run_id>/`へ出力します。schema-v4 manifestは
C2C taskやPLAN iterationを要求しません。

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

## 手動publisher操作

exact threadへ届いたqueue turnは、runtime identityから受信を確認してから
publisherを実行します。receiver thread IDをCLI引数で指定する手段はありません。

```powershell
\.venv\Scripts\python.exe -m sawopt.orchestration.cli confirm-queue `
  --run-dir <RUN_DIR> --run-id <RUN_ID> `
  --delivery-id <DELIVERY_ID> --delivery-sentinel <DELIVERY_SENTINEL>

\.venv\Scripts\python.exe -m sawopt export-review --run <RUN_DIR>

\.venv\Scripts\python.exe -m sawopt.orchestration.cli mark-review-published `
  --run-dir <RUN_DIR> `
  --review-path reports/experiment_reviews/<stage>/<run_id> `
  --branch <EXPERIMENT_BRANCH> --commit <PUSHED_COMMIT_SHA>
```

export完了は`review_evidence_state: EXPORTED`として記録されますが、run自体は
`COMPLETED`/`FAILED`のままです。bundleのcommitとmatching upstreamへのpushを検証した
publication finalizerだけが`REVIEW_WAITING`へ進めます。queue送信または受信の成功は
`REVIEWED`を設定しません。

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
