# Issue #92 — Pi 1.4.0 installed manifest provenance investigation

**Date:** 2026-10-24 JST; **classification:** `MANIFEST_PROVENANCE_UNRESOLVED`; **qualifier:** `NO_HISTORICAL_PER_FILE_BASELINE`; **real Pi starts:** `0`.

**Issue #91:** remains `PI14_DIAGNOSTIC_PREFLIGHT_BLOCKED`; its one-shot authorization remains unused.

This is an append-only static provenance report under Issue [#92](https://github.com/miyabimm/saw-com-optimizer/issues/92). It does not amend the Issue [#89 dossier](https://github.com/miyabimm/saw-com-optimizer/issues/89) or re-baseline its recorded digest. Issue [#91](https://github.com/miyabimm/saw-com-optimizer/issues/91), [#86](https://github.com/miyabimm/saw-com-optimizer/issues/86), [#75](https://github.com/miyabimm/saw-com-optimizer/issues/75), and [#53](https://github.com/miyabimm/saw-com-optimizer/issues/53) remain open/blocked as previously directed.

## Scope and safety

Inspected only the seven installed `@earendil-works` package manifests and regular files below their `dist/` directories. Hashing used Python standard-library file and SHA-256 operations. No installed file was modified. No installed Pi, Node, Bun, module import, Pi entrypoint, RPC/session, provider/model, prompt, HTTP server, package manager, network operation, scientific/optimizer calculation, raw/checkpoint, auth/profile, or session access was part of the package inspection. No project software tests or local regression suite were run. Host installation paths and per-file manifests are intentionally omitted.

The package inventory was read in place and was not archived. The results therefore describe the inventory observed during this inspection; they do not provide an independently preserved historical inventory.

## Recorded and locally observed inventory

The Issue #89 dossier records the original aggregate SHA-256 as
`bd0aa78625c78c1ccc8bfc3597d359ea6dacc0d0ef861dd14c045ea925a70fbf`.
The Issue #92 planning record reports a later aggregate SHA-256 of
`c922de9e118b2649fb4eabb98eeefa84b7c8c618ec6e7b962e781ec4ff527475`
for a sorted seven-package, 2,320-file manifest. Neither record supplies a
complete historical per-file `(relative path, SHA-256)` inventory. The #89
dossier gives selected individual file hashes, not a full package baseline;
no independent #91 per-file baseline was available among the sanitized records
examined for this report.

The current read-only enumeration found:

| Package | Installed version | Included regular files |
|---|---:|---:|
| `pi-coding-agent` | 1.4.0 | 1,095 |
| `pi-agent-core` | 1.4.0 | 25 |
| `pi-ai` | 1.4.0 | 844 |
| `pi-codemode` | 1.4.0 | 65 |
| `pi-mcp` | 1.4.0 | 73 |
| `pi-telemetry` | 1.4.0 | 33 |
| `pi-tui` | 1.4.0 | 185 |
| **Total** |  | **2,320** |

The included set was exactly each package's regular `package.json` and every
regular file recursively under `dist/`, including any maps/data files there;
other package files and directories were excluded. Symlinks under the selected
`dist/` trees and symlinked `package.json` files were not followed; none were
observed in the selected paths. All seven manifests reported version `1.4.0`.

## Explicit current-inventory recipes and results

These are deterministic recipes over the currently inspected inventory, not
proof that a prior operator used the same procedure. In each recipe, individual
file digests are SHA-256 over raw file bytes. Aggregate digests are SHA-256 over
the exact serialized manifest bytes.

| Label | Relative path basis and byte serialization | Current aggregate SHA-256 | Result against recorded value |
|---|---|---|---|
| Current package-root recipe | Paths like `package-name/dist/...` or `package-name/package.json`; paths sorted by Unicode code-point order; UTF-8 rows `<lowercase-file-hex><two ASCII spaces><path><LF>`; LF final terminator. | `bfb904f69f2af82f400729c395ef116ecba4fae32a1f95644ad69a99e1f06226` | Matches neither recorded aggregate. |
| Reconstructed #91 candidate | Paths relative to the `node_modules` root (thus beginning `@earendil-works/package-name/`); same ordering and `sha256sum`-style row bytes as above. | `c922de9e118b2649fb4eabb98eeefa84b7c8c618ec6e7b962e781ec4ff527475` | Exactly matches the #91-reported aggregate on this current inventory. This is a candidate reconstruction, not proof of #91's historical file bytes or exact command. |
| Release-root-relative `sha256sum`-style candidate | Same row format; paths relative to the release root. | `76e5b157121d524082dbbce6ac6282cf079ebefe087c391a9a41c1eb3a4bfb2f` | Matches neither recorded aggregate. |
| Path-first text candidate | Package-root-relative UTF-8 rows `<path><two ASCII spaces><lowercase-file-hex><LF>`. | `49d8b1ae498f79a35baf75417c1b8a5419293e7bb046902eb683d9d8e2d846a3` | Matches neither recorded aggregate. |
| Binary tuple candidate | Package-root-relative UTF-8 path, NUL byte, raw 32-byte file digest, LF; rows sorted by path. | `1f1710b72edcb151a6250d3f487035cc2173aea954239727f69c9f6f1d19b770` | Matches neither recorded aggregate. |

A host-absolute-path form was also checked locally but is not published: it is
host-specific, does not reproduce the #89 value, and would not be a portable
historical recipe. These bounded candidate checks are not an exhaustive format
search. No format match alone is treated as proof of a past procedure.

### Reproduction disposition

- **`OLD_REPRODUCED=NO`.** The #89 digest was not reproduced by the explicit
  current-inventory recipes above. The available #89 dossier does not specify
  byte-level path, ordering, line-ending, separator, encoding, or aggregate
  serialization rules from which its exact procedure can be reconstructed.
- **`NEW_REPRODUCED=YES, WITH LIMITATION`.** The #91 digest is reproduced by
  the explicitly documented `node_modules`-relative recipe on the current
  inventory. The sanitized #91 summary available in #92 supplies no per-file
  inventory, so this does not independently prove that the historical #91 run
  used these exact bytes or that the present files are unchanged since then.
- **`HISTORIC_PER_FILE_BASELINE=NO`.** Neither the available #89 dossier nor
  sanitized #91 evidence includes a trustworthy complete historical
  per-file baseline.
- **Classification remains `MANIFEST_PROVENANCE_UNRESOLVED`** with
  `NO_HISTORICAL_PER_FILE_BASELINE`. The evidence does not satisfy
  `MANIFEST_METHOD_MISMATCH_CONFIRMED` (both historical values have not been
  reproduced from one proven inventory with two historically supported
  byte-level recipes) or `CONTENT_IDENTITY_MISMATCH_CONFIRMED` (there is no
  trustworthy historical per-file comparison localizing changed bytes).

The exact #91 candidate match is useful evidence that path-root/manifest
serialization can account for that reported aggregate on the current
inventory. It must not be elevated to a claim that all installed files are
historically identical, nor used to accept/revise the #89 baseline or release
the #91 gate.

## Authorization and next gate

No code, tests, CI settings, runtime, installed package, or historical evidence
was changed. No digest was substituted into the #89 dossier. `#91` remains
blocked and its one-shot real-Pi authorization remains unused; this report
provides no permission to start Pi, use a provider/model, access RPC/session,
perform replay, or run COM/FE/optimizer work. Independent GitHub review and a
subsequent explicit owner disposition are required before any #91 restart,
identity-gate release, re-baseline, issue closure, or legacy cutover.
