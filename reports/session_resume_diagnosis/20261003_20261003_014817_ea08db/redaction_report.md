# Redaction and publication checks

- Full run paths normalized to <SAW_REPO>; profile paths normalized to <USERPROFILE>.
- Callback prompt body omitted. The callback command is reduced to executable family, exec resume, target ID, and <review-prompt>.
- Full callback.log, stdout.log, Codex JSONL rollout, C2C logs, optimizer results and checkpoint bodies were not copied. Their sizes, mtimes and SHA-256 values are recorded in artifact_inventory.csv.
- No authorization headers, bearer credentials, access/refresh tokens, client secrets, cookies, credentials, OAuth authorization URLs, pairing codes, C2C token prefixes, raw Quick Tunnel URLs, MCP public URLs, or OAuth callback URLs were found by the final pattern scan.
- No unnormalized local profile path is present. Paths are normalized. GitHub repository URL, run/thread IDs, PIDs, commit SHA, and hashes are retained for provenance.
- Every source artifact is excluded from upload; the evidence package contains only 13 text-based forensic files.
- Preservation check after evidence creation: all 242 files in the original production run directory were re-hashed and matched the inventory (6,304,828,522 bytes total; 0 mismatches). This includes manifests, results, logs, and all full final checkpoint files.
- Redaction scan: PASS. Evidence consistency checks: PASS.
