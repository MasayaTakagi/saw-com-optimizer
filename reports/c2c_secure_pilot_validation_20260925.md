# C2C Secure Pilot 検証・Closeout報告

検証日: 2026-09-25 / Closeout日: 2026-09-26
結論: **PASS WITH LIMITATIONS**

固定SHAでのローカル検証、Quick Tunnel、ChatGPT connector/OAuth pairing、ChatGPT経由のMCP検証、read-only tool surface確認、C2C loop検証まで完了した。Closeout時にも`workspace_info`と`git_status`を再確認し、workspace `saw-com-optimizer`、branch `codex/c2c-secure-pilot-20260925`、Closeout開始時HEAD `52a9eb35db16f1cd252b5bbd5fca02ec785d59de`を確認した。本運用への移行を許可する。残る制約は、更新候補が実際にある場合のupdate protection positive caseと、Windows権限制約により作成できなかった通常file symlink escape testである。いずれも本運用開始のBlockerとはしない。

## Environment

| 項目 | 結果 |
|---|---|
| Windows | `cmd /c ver`: `10.0.26200.9550` |
| Codex CLI | `codex-cli 0.155.0-alpha.9.2` |
| Node.js | `v24.19.0` |
| Git | `2.55.0.windows.5` |
| Python | `python` はPATHになし。プロジェクト `.venv` は `Python 3.12.14` |
| Corepack / pnpm | PATH上にCorepack CLIがなかったため、一時起動したCorepack `0.36.0` 経由でpnpm `11.24.0` を使用 |
| cloudflared | `2026.9.3`。`C:\Users\sub\AppData\Local\codex-with-chatgpt\bin\cloudflared.exe`へ配置し、SHA-256を公式release checksumと照合 |
| winget | 未導入 |
| C2C prefs | `setupMode: manual`、`developerModeEnabled: true` |

cloudflaredは次の公式配布物を使用した。ダウンロード物のSHA-256は公式値と一致した: `f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2`。

- [Cloudflare公式Downloads](https://developers.cloudflare.com/tunnel/downloads/)
- [cloudflared公式GitHub releases](https://github.com/cloudflare/cloudflared/releases)
- [Corepack公式npm package](https://www.npmjs.com/package/corepack)

## C2C Baseline

- Repository: `https://github.com/XiaoDuoYa/codex-with-chatgpt`
- Reviewed commit: `9663b88753e35c76796c5bce000293e0bd22cd9e`
- package version: `0.1.3`
- `git fetch origin` 後の `origin/main` とC2C `HEAD` は同じReviewed SHA
- frozen-lockfile install、build、typecheckが成功
- C2C test: **17 files / 178 tests passed**
- install前後の `pnpm-lock.yaml` SHA-256: `70DF031D08DDC23FEADA47A7C8C820B12FB921874F2285F6A00367309D4FA5FB`（不変）
- C2C checkout最終状態: `main...origin/main`、clean

### 正式Security BaselineとVersion Up Gate

| 項目 | 固定値 / 方針 |
|---|---|
| Reviewed repository | `XiaoDuoYa/codex-with-chatgpt` |
| Reviewed SHA | `9663b88753e35c76796c5bce000293e0bd22cd9e` |
| Package version | `0.1.3` |
| Status | `APPROVED WITH LIMITATIONS` |
| Automatic update | 禁止 |
| Dependency update | Security Reviewなしでは禁止 |
| Version Up前 | ChatGPT Security Reviewとユーザー承認が必須 |

次のSecurity Reviewで新しいcommitが承認されるまで、Reviewed SHAを固定する。候補検出後は更新せず、current Reviewed SHAとcandidate SHAを取得してユーザーへ通知する。ChatGPT Security Reviewで`current..candidate`の差分、dependencyとlockfileを確認し、Security PASSおよびユーザー承認を得てから初めてcheckout/updateする。更新後は`pnpm install --frozen-lockfile`、build、typecheck、test、Windows canaryを行い、承認済みの新SHAを次のReviewed Baselineにする。

候補検出時の通知文:

> C2Cの更新候補が検出されました。
>
> Current Reviewed SHA: `<current>`
>
> Candidate SHA: `<candidate>`
>
> Security Reviewが必要なため、現在のReviewed Versionを維持します。

元の作業が現在のReviewed Versionで継続可能な場合はそのまま続け、C2C更新処理は実行しない。

## Phase Gates

| Phase | 状態 | 結果 |
|---|---|---|
| 0 — Baseline | PASS | 開始時は`main`、HEAD `52a9eb35db16f1cd252b5bbd5fca02ec785d59de`。`docs/handoff/`は開始前から未追跡で、変更していない。 |
| 1 — C2C配置・SHA固定 | PASS | 既存の兄弟directory checkoutを利用。指定SHA、remote、clean statusを確認。 |
| 2 — frozen install / build / checks | PASS | `corepack pnpm install --frozen-lockfile`相当を実行し、build、typecheck、178テストが成功。lockfile変更なし。 |
| 3 — 安全なSkill | PASS | upstream `skill/SKILL.md`は不変。CodexインストールコピーだけにReviewed SHA固定、更新検知のみ、Security Review必須、frozen install、cloudflaredのuser-local pathを設定。 |
| 4 — `.c2cignore` | PASS | `.git/`、`.env` / `.env.*`、`runs/**/raw/`、checkpoints、`.ckpt` / `.checkpoint`、`tmp/` / `temp/` / `cache/`、private/secrets/credentials/confidential、`references/licensed/`、ZIPを対象にするルールを確認。`src/`、`tests/`、`docs/`、`handoff/`、README、Markdown、CSV、JSONを対象にする除外ルールはない。 |
| 5 — ignore canary | PASS | ローカルresolverとChatGPT経由MCPの両方でpublic canaryを読み取り・検索できた。`.env` canaryはMCP readで`ACCESS_DENIED_SENSITIVE_FILE`、searchは0件。canary削除済み。 |
| 6 — path escape | PASS | ローカルresolverとChatGPT経由MCPでworkspace外absolute pathを拒否。MCP deny codeは`PATH_OUTSIDE_WORKSPACE`。outside canary削除済み。 |
| 7 — symlink / junction | PARTIAL | junction経由の外部読み取りはローカルresolverで拒否。MCPでは通常のworkspace外absolute path拒否を確認。Windows権限上file symlinkを作成できず、その個別ケースは未確認。 |
| 8 — workspace / sandbox設定 | PASS | workspace rootは`C:\Users\sub\Documents\ChatGPT\saw-com-optimizer`。`sandbox-allow`は`alreadyAllowed:true`で、`config.toml`のSHA-256も前後で不変。`.c2c.json`は作成されていない。`prefs`は`setupMode: manual`、`developerModeEnabled: true`。 |
| 9 — Tunnel / connector | PASS | ユーザーの明示承認後にQuick Tunnelを起動。最新の`doctor`でbridge、MCP、OAuth、tunnelがすべて成功し、ユーザーからChatGPTのConnect完了報告を受けた。公開URLはこの報告へ記録しない。 |
| 10 — ChatGPT経由のMCP確認 | PASS（ユーザー報告） | `C2C CHECK_RESULT: PASS`。workspace名`saw-com-optimizer`、root `workspace:/`、top-level `README.md`読み取り、root list、public read/search、`.env`・`.git/config`・outside path拒否、git status/diffの非開示を確認。 |
| 11 — ChatGPT側tool surface | PASS（ユーザー報告） | connectorには指定9 read-only toolのみ。write/delete/shell/commit/install toolはなし。 |
| 12 — C2C loop | PASS（ユーザー報告＋Git確認） | INIT→PLAN→staged canary→EXECUTED→独立レビュー→cleanup→EXECUTED→DONE。canary削除後、staging空とbaseline状態を確認。Markdown-onlyのためtestsは未実行。 |
| 13 — update protection | SKIPPED（candidateなし） | `update-check --force --json`は`updateAvailable:false`、local/remote SHAは指定Reviewed SHA。更新候補がないため、更新検出後の動作は実地検証できていない。Skillの自動更新禁止ルールは設定済み。 |
| 14 — 最終Regression | PASS | SAW HEADは開始時と同じ。canary不在、staging空、tracked diffは`.c2cignore`のみ。C2C checkoutはReviewed SHAでclean。最新doctorでbridge/MCP/OAuth/tunnelがすべて成功。 |
| 15 — Closeout MCP health | PASS | `workspace_info`で`saw-com-optimizer`、`workspace:/`、branch `codex/c2c-secure-pilot-20260925`を確認。`git_status`でstagingなし、conflictなし、`.c2cignore`のみunstaged、既存の`docs/handoff/`とPilot報告書のみuntrackedを確認。接続面は承認済み9 read-only tools。 |

## Security Validation

- `.c2cignore`付き実workspaceのローカルresolverとChatGPT経由MCPを確認。ChatGPT側のPhase 10/11結果はユーザーがProject会話から転記した`C2C CHECK_RESULT: PASS`に基づく。
- `private/`、`.git/config`、`../`、`..\\..\\`、absolute outside pathは各ポリシーのdeny codeで拒否された。
- Junction escapeは拒否。通常file symlink作成は権限不足でskipし、管理者昇格は行っていない。
- ChatGPT側connectorは指定9 read-only toolのみで、write/delete/shell/commit/install toolがないとユーザー報告で確認。
- Phase 10用canary 3点とPhase 12用一時Markdownはすべて削除し、残存しないことを確認。canary本文は報告へ含めていない。
- ユーザーはworkspace MCP面の公開を明示承認した。Quick Tunnelは起動済みで、`doctor`の公開ヘルス確認に成功した。
- ユーザーがChatGPTのConnect完了とworkspace/MCP検証を報告し、その後の`doctor`でOAuthが正常と確認した。
- pairing code、token、Cloudflare credential、公開URLは報告書へ記録していない。

## Git State

### SAW repository

- 作業branch: `codex/c2c-secure-pilot-20260925`
- Closeout開始時HEAD: `52a9eb35db16f1cd252b5bbd5fca02ec785d59de`
- Closeout開始時status: `.c2cignore` unstaged-modified、`docs/handoff/`と本報告書がuntracked、stagingなし
- Closeout対象: `.c2cignore`と本Pilot報告書のみ
- `docs/handoff/`は既存の未追跡状態を保ち、変更・stage・commitしていない
- Pilot canaryは残存しない。SAW source、tests、optimizer、COM modelに変更なし
- Closeout commitはPilot branchのみ。Mainへのmerge/pushおよびStage 3.8再開は行わない

### C2C repository

- final HEAD: `9663b88753e35c76796c5bce000293e0bd22cd9e`
- branch: `main`、status: clean（Closeout時にread-onlyで再確認）
- upstream sourceは変更していない

## Limitations

C2Cの`setupMode`は`manual`、`developerModeEnabled`はtrue。connector/OAuth、Project、Project instructions、会話URLのsession登録は完了。`update-check --force`で`updateAvailable:false`のため、`updateAvailable:true`検出後に通知のみ行い、自動pull/install/build/restartしないpositive caseは未実地。**最初に新しいupstream commitが検出された時点で検証する。** それまではReviewed SHAを維持する。

Windows権限制約で通常file symlinkは作成できず、そのescape caseは未確認。`../` traversal、absolute outside path、Windows-style traversal、junction escapeは拒否を確認済み。管理者権限を追加してこのテストを行わない。C2C checkoutとSkillはReviewed Baselineのまま。

## Conclusion

**PASS WITH LIMITATIONS**

本Pilotでは、Reviewed SHA固定、frozen-lockfile dependency install、build/typecheck/test成功、read-only MCP、workspace containment、`.c2cignore` enforcement、`.git/config`とsensitive fileの拒否、OAuth/connector接続、C2C loop、SAW repositoryの不要なsource変更がないことを確認した。Closeout時のMCP `workspace_info` / `git_status`もPASS。C2Cの承認済みtool surfaceは9 read-only toolsで、write/delete/shell/commit/install toolを含まない。

**本運用開始を許可する。** Reviewed SHA固定、自動update禁止、Version Up前Security Review、frozen dependency install、`.c2cignore`維持を継続条件とする。

残余項目:

1. `updateAvailable=true`のpositive case（次のupstream commit検出時に確認）
2. Windows通常file symlink escape

どちらも本運用開始のBlockerとはしない。Operational status: **APPROVED FOR NORMAL SAW DEVELOPMENT USE**。AUTO UPDATE: **DISABLED**。
