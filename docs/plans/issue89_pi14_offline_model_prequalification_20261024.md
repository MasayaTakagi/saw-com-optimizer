# Issue #89 — Pi 1.4.0 offline dummy-model static/fake prequalification

**Date:** 2026-10-24 JST  
**Status:** `PI14_STATIC_AND_FAKE_EVIDENCE_RECORDED; INDEPENDENT_REVIEW_PENDING` — static source findings and Python fake-fixture evidence only.  
**Binary recommendation:** `SAFE_TO_PROPOSE_ONE_RUNTIME_DIAGNOSTIC` is a proposal only, **not permission** to launch Pi. A real Pi process using this changed model configuration, any RPC/session, prompt, provider request, or model API remains unauthorized. Issue #86 remains `REAL_PI_OFFLINE_TEST_BLOCKED`; #75 and #53 remain open.

## Scope and result boundary

This work followed Issue #89 and its owner comment. It read the installed Pi 1.4.0 distribution and installed Pi 1.4.0 dependencies as files only. It did not start Pi, Node, Bun, a Pi RPC/session, provider/model API, or local server, and it did not read the personal Pi configuration, session, or auth stores.

**Execution-scope deviation and owner disposition:** project Python processes were run: `uv sync --locked --extra test` (which provisioned the worktree-local `.venv`), the focused fake pytest, full pytest, Q1-A verification/import-guard scripts, SAWOpt CLI help, and `compileall`. The full suite also ran test-owned Python subprocess fixtures. At the time, the `コード不実行` wording conflicted with the issue body directing fake tests and full regression. The owner explicitly accepted the reported Python activity as test-only software-validation evidence subject to independent review, clarified the no-run boundary as excluding real Pi/Node/Bun, provider/model/API, prompt, RPC/session, local server and scientific/legacy activity, and authorized only the two-file commit/push, Draft PR, and ordinary exact-HEAD GitHub CI ([owner disposition](https://github.com/miyabimm/saw-com-optimizer/issues/89#issuecomment-6379383941)). This is not independent verification of the local results or a retroactive claim that the directions were consistent before execution. No further local execution is authorized. No Pi, Node, Bun, RPC/session, provider/model request, or local server was started. Package-manager network activity from `uv sync` was not independently measured, so no claim is made that the environment had zero network traffic.

The source supports a narrow conclusion: a fictitious custom provider and model can be configured using a literal dummy key and a loopback-only endpoint; Pi's source can construct and select that model without sending a model request. `--offline` disables startup catalog network operations, but is **not** a network sandbox. A future diagnostic must prove the OS-level offline boundary independently and use only a fresh private profile. The source inspection and fake tests do not qualify actual Pi config parsing, Pi startup, RPC wire behavior, session persistence, or exact-session identity.

## Installed-source identity

The installed coding-agent package reports version `1.4.0`. All seven directly installed `@earendil-works` packages inspected (`pi-coding-agent`, `pi-agent-core`, `pi-ai`, `pi-codemode`, `pi-mcp`, `pi-telemetry`, `pi-tui`) report version `1.4.0`.

Hashes below were calculated from installed code/manifests, not from user config or session data. Paths are relative to the installed release package root; the host-specific installation path is intentionally omitted.

| Identity | SHA-256 |
|---|---|
| `pi-coding-agent/package.json` | `df6883685382d6a914e5797232744c26579fe7db5576ea0e9c859d018ca2d54e` |
| Sorted per-file SHA-256 manifest of `pi-coding-agent/dist/**` (aggregate digest) | `0798da7a0cccb6c3ebb84fb25b6e71e18af52b723f8de4283647056edcc4f3bb` |
| Sorted per-file SHA-256 manifest of `dist/**` and `package.json` for all seven installed `@earendil-works` packages (aggregate digest) | `bd0aa78625c78c1ccc8bfc3597d359ea6dacc0d0ef861dd14c045ea925a70fbf` |
| `pi-coding-agent/dist/bundle/cli.js` | `e79626f2dd6f94aa45d30f3fa63cd84319a6eefcd150b353cfaf274366926774` |
| `pi-coding-agent/dist/main.js` | `08b91f9eb3adf9a5027c18732d1e4de70999bd15c445b65cb0ddd0cd68f2746b` |
| `pi-coding-agent/dist/core/model-config.js` | `b4ecb1165c328fdb5f8b767519f2b632c31737f86d0ce1d7a05959e7c8354d93` |
| `pi-coding-agent/dist/core/model-resolver.js` | `5b7172bd17f1a3c61e4e5187b400966f471e344623389b8876b099b4948ae1b3` |
| `pi-coding-agent/dist/core/model-runtime.js` | `44d8017928eff6721d5a56b4e71f98bcafb124f5aa6e7d3f016491e11fcf6461` |
| `pi-coding-agent/dist/core/provider-composer.js` | `7ec4af06726158fa34377bed34fbb378d2d39c5c9d51ae5640ac459a4c78bec4` |
| `pi-coding-agent/dist/core/resolve-config-value.js` | `01fdb1673990635bb419c7418eefa298b6a1c6fbb3c6193d3b05a4902e51992d` |
| `pi-coding-agent/dist/migrations.js` | `8514d2573b028baeba60635498a1c5f129a602abd203ea5c37a63df2eea3fb6b` |
| `pi-coding-agent/dist/core/resource-loader.js` | `ad50235884ea6d5ee14cdae1efcfe6afef58b22b18ce574e81886d57ca9f4642` |
| `pi-coding-agent/dist/modes/rpc/rpc-mode.js` | `631697cd35928fc827f4a423538c43ff227b8cbf63c2a2f11060616f55eba6db` |
| `pi-ai/dist/models.js` | `de6323034ca216eefecdfc44dd5c93f22713b34a01f2eb21a6d0a5ce85f9bb19` |
| `pi-ai/dist/auth/resolve.js` | `3fcec09018831324d9c7fb02f4aea707e8a9e4fec5a2bdf1b3d84d716fd3091e` |

## Static source findings

### Startup, model selection, and RPC boundary

- `dist/cli/args.js:41–57, 66–68, 99–100, 108–109, 160–165, 188–198, 235–236` parses the relevant flags. The installed help text is generated from that same file (`:293–336`): `--model`, `--session-dir`, `--mode rpc`, `--offline`, `--no-tools`, `--no-extensions`, `--no-mcp`, `--no-skills`, `--no-prompt-templates`, `--no-themes`, `--no-context-files`, and `--no-approve` are supported in this version.
- `dist/main.js:455–458` implements offline mode by setting `PI_OFFLINE=1` and skipping the version check. The RPC catalog refresh is skipped when offline (`:765–772`). The CLI reference explicitly defines `--offline` as disabling **startup network operations** (`dist/cli/args.js:336`); it does not enforce network isolation and does not prevent a later prompt/model call.
- A normal command runs migrations before normal argument handling (`dist/main.js:532–535`; `dist/migrations.js:300–308`). The migrations can read or mutate agent/profile files, including legacy auth/settings, sessions, keybindings, extension/prompt directories and managed binaries (`dist/migrations.js:19–69, 74–…`). Therefore a future invocation must put `HOME`, `PI_CODING_AGENT_DIR`, XDG paths, cwd, temp, and session storage inside a fresh disposable root before launching Pi. The root must be the only writable profile/workspace exposed; do not infer that flags alone avoid filesystem effects.
- `getAgentDir()` honors `PI_CODING_AGENT_DIR` before falling back to the homedir (`dist/config.js:490–496`); auth, settings, models, skills, themes, tools, prompts and sessions derive from that directory (`:502–528`). `--session-dir` overrides session storage in normal startup (`dist/main.js:550–554`). This is the supported route to keep config/session access in the disposable profile, but it is not a substitute for hiding host paths.
- `ModelRuntime.create()` reads the selected `models.json`, composes providers and calls refresh (`dist/core/model-runtime.js:79–112`). The CLI does not enable network refresh on runtime creation; service setup and model refresh pass `allowNetwork: false` (`dist/core/agent-session-services.js:53–70, 111`). `pi-ai/dist/models.js:180–208` passes `allowNetwork` into provider catalog refresh and returns before the network credential/catalog phase when false. The fake provider below has no catalog-fetch hook.
- Availability is not purely a parse: startup refresh asks the model library for available models, checks auth on installed providers, and lists credentials (`dist/core/model-runtime.js:189–213`; `pi-ai/dist/models.js:250–…`). The fake provider's auth check uses its configured literal key without resolving env or executing a command (`dist/core/provider-composer.js:225–285`). Stored credentials are read through the configured auth store; ambient credential sources are provider-specific. The future `env -i`, private home/profile and no-host-path sandbox are required; this report does not claim the whole runtime has no credential reads or file side effects.
- The explicit CLI resolver uses **all catalogued models**, not only pre-authenticated models, so `--model <provider>/<model>` can select a custom entry (`dist/core/model-resolver.js:308–350`). Independently, `findInitialModel()` chooses from the available snapshot and otherwise returns no model (`:377–427`). With the literal dummy key, the custom provider reports configured auth and its model enters the available snapshot. This is a local status check, not proof that the dummy credential is valid.
- The no-model guard for non-interactive modes precedes RPC dispatch (`dist/main.js:756–776`). `--model` selects the unique fictitious model; if that selection fails, the future diagnostic must stop rather than fall back to another provider/model.
- The read-only `get_state` RPC handler only reads session fields and returns a response (`dist/modes/rpc/rpc-mode.js:342–360`). Do not send `prompt`, `steer`, `follow_up`, or any request that can invoke a model. This static handler inspection does not prove full RPC initialization is side-effect-free.

### `models.json` and credential resolution

- The installed 1.4.0 `dist/core/model-config.js:33–97` defines the model/provider schema; `ModelConfig.load()` reads, parses, validates, clones and freezes the JSON (`:125–158`). The provider accepts `api`, `baseUrl`, `apiKey` and `models`; a custom chat model needs a model `id`, and provider composition requires an API family and base URL (`dist/core/provider-composer.js:83–117`). Installed version-pinned reference: `docs/models-configuration.md` in the same 1.4.0 package.
- `apiKey` is not a benign opaque field for arbitrary values. In this installed version, strings beginning with `!` can execute a shell command and `$NAME` / `${NAME}` can read environment variables (`dist/core/resolve-config-value.js:21–69, 117–128, 130–187`). Do not use either form anywhere in this fixture; do not add `headers` or model overrides.
- `composeApiKeyAuth().check()` treats a nonempty literal as configured without resolving or calling it (`dist/core/provider-composer.js:225–285`). Resolution occurs on the request path (`:286–326`; `dist/core/model-runtime.js:369–383, 452–487`). A stored credential for the same provider can take precedence, so the profile must be fresh and contain no auth entries. A fake key is intentionally *classified as configured* so the dummy model becomes selectable; it is not an authenticated-provider result and must never be sent.
- The `pi-ai` auth resolver first checks a stored credential and only then ambient auth (`pi-ai/dist/auth/resolve.js:14–44`). The model request path resolves an API key, while this proposal sends no model request. The fake provider ID is not a built-in provider and the fake base URL is loopback-only.

### Startup resources and hidden effects

- `--no-tools` disables all session tools (`dist/cli/args.js:108–109`; session options in `dist/main.js:678–701`).
- `--no-extensions` removes discovered/configured extension paths, including built-in extension paths; `--no-mcp` separately disables the built-in MCP extension (`dist/core/resource-loader.js:63–65, 247–267, 406–412`; `dist/main.js:636–645`). Do not pass explicit `--extension` paths. The CLI calls `main(args)` without programmatic extension factories (`dist/cli.js:1–3`), so the separate SDK-only inline-factory path is not active for the proposed CLI invocation.
- RPC startup normally runs after resource loading/session creation. MCP connects from a `session_start` handler only if the MCP extension is loaded and the private profile configures enabled servers (`dist/extensions/mcp/index.js:971–1008`). With an empty private profile plus `--no-extensions --no-mcp`, that path is excluded. The network namespace remains mandatory even with these flags.
- These flags do not neutralize migrations or all file access. The proposed disposable profile/workspace must be isolated before Pi starts. A requirement to make the profile, rootless namespace, no-route state, resource disabling or bounded stderr less strict is a STOP condition.

## Minimal illustrative dummy config

This is a **design snippet only**, not a checked-in Pi config and not a claim that Pi parsed it. The Python fake test writes an equivalent object only to a fresh temporary profile (0700 directory, 0600 file), then deletes it. It has no executable credential hook, environment reference, real provider name, external API host, secret, listener, or prompt.

```json
{
  "providers": {
    "sawopt-pi14-offline-test-only": {
      "name": "Pi 1.4.0 static preflight dummy",
      "baseUrl": "http://127.0.0.1:9/v1",
      "api": "openai-completions",
      "apiKey": "SAWOPT_PI14_DUMMY_NOT_A_SECRET",
      "models": [
        {
          "id": "sawopt-pi14-dummy-model",
          "name": "Offline dummy model"
        }
      ]
    }
  }
}
```

The API string is the installed Pi protocol/API family identifier, not a provider ID. The provider and model identifiers are fictitious. `127.0.0.1:9` is only a syntactically valid loopback target; no service may listen there. The proposed runtime namespace must keep loopback DOWN and have no routes. If that cannot be objectively checked inside the same namespace before Pi starts, do not start Pi. The literal dummy key is not accepted by any actual provider and exists only because 1.4.0 treats a configured literal key as evidence of configured auth; a prompt/request is prohibited.

## Static/fake-only fixture contract and checks

`tests/unit/test_pi14_offline_model_fixture.py` is isolated test code, not a Pi integration or product API. It uses Python standard-library JSON, path, socket and file-permission primitives plus pytest's `tmp_path` fixture. Its narrow fake resolver checks the design contract:

- create only under a private temporary profile and remove it automatically; enforce profile mode 0700 and config mode 0600;
- accept the exact dummy provider/model/API/key and loopback URL above; select only that exact model, with no default/fallback provider;
- reject missing/malformed/incorrect-shape config and a missing model or dummy key;
- reject any `$ENV` or `!command` credential string, non-fictitious provider/model identity, non-loopback host, and altered endpoint;
- reject symlinked config, path traversal, a config outside the expected profile, an unexpected profile root, or insecure file/directory permissions before opening config content;
- reject any modeled preflight whose network-isolated prerequisite is false; a socket stub makes accidental network use by the **fake Python resolver itself** fail the test;
- prove that a dummy environment value is not consulted as a fallback by the fake resolver.

These are tests of our safety checklist and temporary-file handling only. The fake resolver is not the installed Pi parser, auth system, availability snapshot or `findInitialModel`; its tests do not establish Pi runtime correctness, OS namespace isolation, secret scanning of the whole host, or network isolation. No Node/Pi code is imported or executed by these tests.

## Proposed future single diagnostic — proposal only

A later, separately owner-disposed request could propose **one** bounded Pi 1.4.0 startup for a no-prompt diagnostic, with the model/config above. This issue does not authorize it. Before any such start:

1. Prove rootless user/mount/network/PID namespaces. In the exact network namespace, verify loopback is DOWN and there are no routes. `--offline` / `PI_OFFLINE=1` are supplementary, not evidence of disconnection.
2. Use a new private 0700 chroot/HOME/XDG/config/session/cwd/temp root. Expose only exact Pi 1.4.0, the already-existing Node runtime and required libraries read-only; do not mount the host home, any existing Pi profile/session, repository/worktree, raw/checkpoint, sockets, extension/MCP config, provider credentials or user data. Keep the isolated profile/workspace as the only writable locations.
3. Use `env -i` with only required runtime path variables and test-only `HOME`, XDG locations, `PI_CODING_AGENT_DIR`, and session-dir. No inherited credential variables, `auth.json` entries, sockets, or secret stores. Add `PI_OFFLINE=1` plus `--offline`, `--mode rpc`, explicit `--model sawopt-pi14-offline-test-only/sawopt-pi14-dummy-model`, `--no-tools`, `--no-extensions`, `--no-mcp`, `--no-skills`, `--no-prompt-templates`, `--no-themes`, `--no-context-files`, `--no-approve`, and an explicit test-only `--session-dir`. Do not pass an extension, project path, message, prompt or model API invocation.
4. Send only one read-only `get_state` RPC request. Treat any attempt to prompt, resolve an unexpected model/provider, load a resource outside the fixture, contact an API, create a child server, or access an external path as a failed preflight and stop. Never retry or weaken isolation.
5. Bound to at most 15 seconds wall time, 12 CPU seconds, 3 GiB memory; cap process/file descriptors and ensure process-group/PID-namespace cleanup. Capture stderr separately in a fresh 0600 private file/buffer of at most 8 KiB with a truncation marker; drain pipes without deadlock. Do not publish raw stdout/stderr, env, absolute paths, config contents, model outputs or secrets. Delete temporary artifacts after preparing only sanitized status/diagnostic-category evidence.

Even a future successful invocation would establish only a bounded diagnostic startup/in-memory `get_state`, not a saved exact session, reopen, branch continuity, prompt replay, provider/model API qualification, Pi-RPC general integration, or scientific FE recovery. If the isolated environment cannot prove every required condition, report `OFFLINE_MODEL_AVAILABILITY_BLOCKED` and stop without launching.

## Risk / stop matrix

| Risk | Static evidence / control | STOP if |
|---|---|---|
| Startup selects no model and exits before RPC | Explicit fake `--model` maps to configured catalog entry; no-model guard is pre-RPC. | Model is not uniquely resolved, or Pi proposes a different model/provider. |
| Key executes shell or reads ambient secret | Literal exact dummy only; reject `$` and `!`; private empty auth store; `env -i`. | Any interpolation, command, keyring, environment, or stored credential is needed. |
| Hidden startup request | `--offline` gates catalog refresh; custom fake has no refresh hook; no prompt; `get_state` is local. | Any provider/model API or network path is needed, or route isolation is uncertain. |
| Extension/MCP/tool execution | No explicit extension; `--no-extensions --no-mcp --no-tools`; no skills/templates/context. | A disabled feature still initializes an untrusted/resource extension or any server. |
| Migrations or writes touch user data | Migrations run before normal flag handling; put all writable roots inside fresh chroot and keep host paths unmounted. | Any user/home/worktree/raw/session path is visible or writable. |
| Resource limit / diagnostic leak | One process; bounded wall/CPU/memory/FD/PID and ≤8 KiB private stderr. | Capture cannot be bounded/redacted, process survives cleanup, or limits need weakening. |

## Checks and remaining uncertainty

- Static-only inspection of installed 1.4.0 generated distribution, installed model-configuration reference and installed `pi-ai` 1.4.0 dependency; content hashes above.
- `uv run --locked pytest tests/unit/test_pi14_offline_model_fixture.py` was first attempted before provisioning the test extra and failed to spawn `pytest` because it was absent. After `uv sync --locked --extra test` created the worktree-local `.venv` and installed the locked test dependencies, the focused command passed: **19 passed**.
- Full locked suite: `OPENBLAS_CORETYPE=Haswell uv run --locked pytest` — **749 passed, 1 skipped**. This includes existing repository regression tests; no new study/data or production workload was launched.
- Q1-A public: `uv run --locked python scripts/verify_stage5a2_canonicalization_golden.py --mode public`; leaf: same script with `--mode leaf` — **92/92 each**; canonical corpus SHA-256 `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2`.
- Preserved Q1-A fixture SHA-256 checks: canonicalization `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2`; Q0 design-space `c7902e30f7becf2e2c0aa280d8f51c25f31f524cbf06c3516252bf47b2faddc9`; Q1-A seed `1a824a07a6e7d652f47388e6604889e612c2809704b7681df713bb9ec8c7087a`.
- Fresh-process import guards `uv run --locked python scripts/check_stage5a2_foundation_imports.py` and `uv run --locked python scripts/check_stage5a2_pure_leaf_import.py` both passed with no forbidden imports. `uv run --locked python -m sawopt --help`, `uv run --locked python -m compileall -q src tests`, and `git diff --check` passed.
- **No Pi, Node, Bun, RPC, provider/model request, or HTTP server was launched.** Python tests and related project commands were run; package-manager network activity was not independently measured. See the execution-scope deviation above. The fake fixture tests do not exercise Pi 1.4.0.
- The prior Issue #86 exit 1 remains unclassified because its stderr was not retained. This static design does not rewrite that evidence or claim it proves the exact failure cause.
- No science, optimizer, FE, legacy queue/callback, historical raw/checkpoint, or project CLI/runtime behavior changed.
