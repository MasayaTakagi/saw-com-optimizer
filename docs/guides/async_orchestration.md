# 非同期本番探索

30分以上かかる見込みの探索は `sawopt.orchestration` を介して起動します。
既存のCOM・Optimizer・同期CLIを直接長時間実行せず、launcherがmanifestを保存した後にworkerが別プロセスで探索を実行します。

新規productionのactive contractは **queue-native exact-thread continuation** です。Stage 4Bで使われた dedicated legacy `codex exec resume` callback はhistorical compatibilityとして読み取り可能ですが、新規productionでは使用しません。

データ保存、ログ、GitHub review evidenceの全体方針は [`data_storage_logging_review_policy.md`](data_storage_logging_review_policy.md) を参照してください。review artifactの詳細は [`postrun_review_contract.md`](postrun_review_contract.md)、review rolesは [`github_review_workflow.md`](github_review_workflow.md) に従います。

## 起動前

本番runでは、対象config、実装、budget、seed、checkpoint方針、外部raw出力先、review-evidence contract、preflightをGitHub上で確認できるbranch/commitに保存します。run自体はユーザーが明示的に承認した後に開始します。

新規productionではdetach前に **exact original Codex thread ID** を取得しmanifestへ固定します。session IDとthread IDは別identityであり、queue targetへsession IDを代用しません。

```text
continuation_mode = queue
original_thread_id = <exact thread id>
```

新規のuser-authorizedまたはranking-eligible productionでは、raw runの保存先にabsoluteな外部persistent root/pathを明示します。通常は既存の保存rootを `--run-root` で渡し、run IDをその直下に作成します。`--run-dir`を使う場合もabsolute pathが必要です。

保存先は全登録worktree、`.git`、review publication path、Windows reparse point、保存先一意性、parent書き込み可否をlaunch前に検査します。Git worktree検出やpath検査に失敗した場合はlaunchを止め、repository `runs/`へfallbackしません。manifestには `external_persistent_v1`、persistent root、repository root、launch元worktreeを記録します。

active-run registryが未初期化・不正・unreconciledの場合もproductionをfail closedします。

## 起動

新規manifestはschema v4です。continuationの既定値は`queue`で、明示的な`--no-callback`は`disabled`として記録します。`legacy_resume`は過去manifestの読み取り・復旧に限り、新規launchでは拒否されます。

queue modeでは`CODEX_THREAD_ID`が必須で、任意の`--thread-id`はその値と一致しなければなりません。`--session-id`と`--session-file`はqueue routingに使用できません。

概念上のlaunchは次の形です。

```powershell
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli launch `
  --config <PRODUCTION_CONFIG> `
  --thread-id <EXACT_ORIGINAL_THREAD_ID> `
  --review-stage <STAGE> `
  --review-spec <FROZEN_SPEC_ID> `
  --run-root <ABSOLUTE_PERSISTENT_RUN_ROOT>
```

ただしroutine productionをユーザー側PowerShell手作業に依存させません。通常はCodex orchestrationがlaunch、storage validation、manifest確認を担当します。

launch時に保存先の外部性と一意性を確認したうえで、Codex実行ファイル/version/helpのpreflightを行い、有限queue timeoutとfrozen review specをmanifestへ保存します。preflightが失敗した場合はrun directoryを作成せず停止します。

launcherは `run_id`、worker PID、run directory、continuation modeを表示して終了します。detached worker開始後に `stdout.log` をpollしたり、完了までforegroundで待機したりしません。

起動直後に `run_manifest.json` を確認し、少なくとも以下がlaunch authorizationと一致することを確認します。

- exact production source SHA;
- config/protocol identity;
- external output path;
- `run_storage_policy: external_persistent_v1`;
- `continuation_mode: queue`;
- exact `original_thread_id`;
- durable one-shot delivery metadata;
- post-run review destination/contract.

identityや設定が指定と異なる場合は、そのlaunchを有効なproductionとして扱わず、別runを自動起動しません。

## 状態確認と復旧

`status` / `recover` / optimizer resume等はactive implementationのqualified contractを使用します。

既存runの数値checkpoint recoveryと、完了後のCodex continuationは別概念です。

- **optimizer recovery/resume:** 同じrun directory/checkpointから数値探索を復旧する。
- **thread continuation:** 完了状態を元のCodex threadへ通知し、evidence publisherを再開する。

完了済みqueue-native runを新規productionとして再launchして同じ計算を再実行してはいけません。

one-shot queue deliveryが曖昧になった場合はfail closedとし、証拠なしに同じmessageを再送しません。

Optimizer child が非zeroで終了した場合、detached worker はそのexit code
を記録し、orchestration state と optimizer state の両方を `FAILED` にします。
セルの失敗記録には例外型、message、repr、tracebackまたはそのrun-local参照、
失敗セル、最後に保存済みのcheckpoint/budgetを残します。`MemoryError` は
空messageになり得るため、`str(exc)` だけを診断情報として使いません。

worker が先に終了し optimizer child がまだ動作中なら、`recover` は
`ORPHANED_CHILD` とし、二重起動やactive-run registryの解除をしません。
両プロセスが停止していてもworkerがexit codeを保存できていない場合、`recover`
は `ORPHANED` と `optimizer_state: UNKNOWN` を記録し、既存checkpoint/run
completion evidenceを書き換えません。

通常の科学review exporterは完走したterminal cell matrixを要求するため、
不完全なorphaned runを科学review済みとして扱ってactive markerを解除してはいけません。
再開しないことを明示的に決めたproduction failureは、GitHubでreview/merge済みの
`reports/administrative_run_closeouts/<run_id>.json` によるrun-scoped authorizationを
用意した後、`close-orphaned-failure --confirm-abandon` で管理上closeします。
詳細は [`administrative_failure_closeout.md`](administrative_failure_closeout.md) を参照してください。

このfinalizerはrun ID、production source SHA、absolute run directory、記録PID、
Git HEADに含まれるcloseout record、clean worktree、両processのdead状態、active-run
registry identityをすべて再検証します。成功時のみrun-localの
`administrative_failure_closeout.json`と`optimizer_completion.json`をdurableに保存し、
orchestration stateを`FAILED`へ遷移した後、exact active-run markerを解除します。
checkpoint、cell artifact、log、authorization claimは削除・改変せず、queue continuationも
送信しません。この管理closeoutはscientific reviewやreplacement productionのauthorizationを意味しません。

## Post-run continuation

標準flowは次の通りです。

```text
optimizer COMPLETED / FAILED
→ durable completion evidence
→ one-shot queue claim
→ codex queue --thread <original-thread-id> --message <bounded handoff>
→ same original thread continuation
→ lightweight review evidence export
→ commit / push
→ publication finalizer
→ REVIEW_WAITING
→ STOP
```

sender側のexit 0だけでsame-thread deliveryを証明したことにはしません。receiver evidenceを取得できる場合はexact thread/delivery identityを確認します。

continuationされたCodexの仕事はreview evidenceのpublisherです。外部review前に次を自動実行しません。

- topology/designの最終promotion;
- `current_baseline.md` の科学判断更新;
- roadmap gateの完了扱い;
- 次のproduction run開始;
- PR merge.

## Queue sender診断

queue senderが非zeroで終了した場合、run-local persistent storageへbounded/redacted diagnostic evidenceを保存します。少なくともexit code、timestamps、stdout/stderr hash、bounded excerpt/truncation、実行ファイル/version identityを保持します。

credential、cookie、OAuth code、reusable token、temporary public endpointは保存・commitしません。

## Review evidence publication

新規runのcanonical destinationは次です。

```text
reports/experiment_reviews/<stage>/<run_id>/
```

raw orchestration/optimizer outputは外部persistent run rootに残し、GitHubにはsummary/manifest/config/protocol/integrity/terminal cell results/convergence/boundary/runtime/limitations等の軽量evidenceをcommitします。巨大なcheckpoint、population dump、cache、raw dense array、full stdout/stderr、callback/Codex rollout logは原則commitしません。

publisherが使う標準操作は以下です。

```powershell
.\.venv\Scripts\python.exe -m sawopt.orchestration.cli confirm-queue `
  --run-dir <RUN_DIR> --run-id <RUN_ID> `
  --delivery-id <DELIVERY_ID> --delivery-sentinel <DELIVERY_SENTINEL>

.\.venv\Scripts\python.exe -m sawopt export-review --run <RUN_DIR>

.\.venv\Scripts\python.exe -m sawopt.orchestration.cli mark-review-published `
  --run-dir <RUN_DIR> `
  --review-path reports/experiment_reviews/<stage>/<run_id> `
  --branch <EXPERIMENT_BRANCH> --commit <PUSHED_COMMIT_SHA>
```

export完了はreview evidenceを生成したことを示しますが、それだけでは科学review完了ではありません。matching branchへのcommit/pushとpublication finalizerが成功した正常handoff stateは `REVIEW_WAITING` です。

## Review state semantics

数値runの完了とscientific reviewを分離します。

```text
COMPLETED / FAILED
CONTINUATION_PENDING
CONTINUATION_SENT
REVIEW_WAITING
```

`REVIEW_WAITING`は外部review待ちであり、`REVIEWED`や科学的acceptanceを意味しません。external ChatGPT review後のscientific dispositionはGitHub closeout、experiment register、baseline/roadmap更新等で記録します。

## Legacy compatibility

historical runには `codex_session_id`、legacy callback state、`callback.log`、`codex exec resume` provenance等が残る場合があります。これらを破壊しません。

ただし新規productionではlegacy resumeを選択しないことをpolicy gateとします。historical manifestのread/recovery compatibilityとactive launch policyを混同しません。

## Current production infrastructure gate

現行mainでは次のproduction infrastructure contractを前提とします。

1. queue-native exact-thread continuation;
2. C2C-only metadataへの必須依存なし;
3. new-launch `legacy_resume`禁止;
4. generic `export-review`によるcanonical review directory生成;
5. one-shot delivery / completeness / redaction / size gate;
6. external persistent raw storage;
7. initialized active-run registry;
8. fail-closed worktree safety;
9. reviewed administrative closeout path for dead orphaned production runs.

これらのいずれかが壊れている、未初期化、または再検証不能な場合は新しい長時間productionを開始せず、そのinfrastructure blockerを先に解消します。

Stage固有のproductionは、これとは別にfrozen protocol/config/review specと明示的なユーザーauthorizationを必要とします。
