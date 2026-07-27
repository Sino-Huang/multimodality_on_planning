# DoneClaim - Authoritative Output-Layout Filesystem-Security Repair

## Status

All six blockers in `review/security.md` are resolved with synthetic-only
regressions, red-green proof, and conservative no-clobber cleanup behavior.

## A-F Resolution

- A: Snapshot and protected-content regular-file reopens include `O_NONBLOCK`.
  FIFO substitutions are rejected after descriptor validation by the public
  inventory/view errors.
- B: The extracted stage scanner and fsync walker share explicit depth and
  per-directory-entry limits with bounded traversal errors.
- C: `create_tree()` records each owned mutation incrementally and propagates a
  `StageConstructionError` carrying that ledger, so cleanup preserves the
  original construction error and removes only still-owned entries.
- D: Stage and receipt quarantine deletion revalidate identity immediately
  before terminal removal. A mismatch retains the quarantine evidence.
- E: A post-publish final identity mismatch remains a normalized view failure;
  cleanup only considers the original stage name and never deletes a racer
  replacement at the public final name.
- F: Every recovery sidecar read, recovery, and cleanup route requires exact
  `0600`; `0644`, `0660`, and `0604` are rejected, while `0600` succeeds.

## Red-Green Proof

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_acceptance_security.py tests/phase3/test_output_layout_receipt_adversarial.py tests/phase3/test_output_layout_snapshot_adversarial.py tests/phase3/test_output_layout_view_fs_adversarial.py tests/phase3/test_output_layout_view_races.py
```

- RED: `12 failed, 81 passed in 0.98s` in `50-authoritative-security-red-pytest.txt`.
- GREEN focused: `93 passed in 0.84s` in `51-authoritative-security-focused-green-pytest.txt`.
- GREEN full: `190 passed in 1.62s` in `52-authoritative-security-full-green-pytest.txt`.

## Diagnostics And Manual QA

- The active Basedpyright LSP returned no diagnostics for every changed Python
  file. Command-line Basedpyright evidence is recorded separately in
  `54-authoritative-security-basedpyright.txt`.
- Synthetic-only manual QA: `synthetic_authoritative_security_qa.py`, recorded
  in `53-authoritative-security-synthetic-qa.txt`. It invokes only `tmp_path`
  scenarios covering A-F and never supplies a real `outputs/` path: `18 passed
  in 0.34s`.
- `55-authoritative-security-no-excuse.txt` reports no production-rule
  violations, including the 250 pure-LOC ceiling.

## Scope Attestation

No task command read, wrote, moved, relinked, hashed, or inspected real
`outputs/` contents. Production and test paths use synthetic `tmp_path` trees.
No plan file or unrelated dirty file was modified.
