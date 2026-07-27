# DoneClaim - Wave 1 Output-Layout Repair 2

## Status

PASS. Current Repair 2 verification closes the accepted Wave 1 output-layout findings.

## Finding Closure

- Cleanup is retention-only: failed stages use durable no-replace `<stage>.cleanup` transitions and receipt sidecars use unique `.retained-<token>` evidence transitions with parent fsync. No terminal cleanup pathname deletion is used.
- The private and published trees are exact-validated after stage fsync and immediately before/successful no-replace publication.
- Snapshot, protected-content, and stage traversal have cumulative work/entry accounting; snapshot and protected-content account actual bytes read.
- Sidecar-read descriptors close on all exits, including oversize domain errors. Direct regressions observe closure plus creation-time exact `0600` modes for `.txn` and `.swap`.
- Transaction parsing is strict without suppressions, and focused test families satisfy the 250 pure-LOC gate.

## Approved Red Baseline

`../task-1-3-security-hardening/review/security.md` and `../task-1-3-security-hardening/review/code-quality.md` remain approved independent pre-fix red-baseline artifacts. Their historical FAIL verdicts are not claimed to have changed. Existing red/green proof receipts remain untouched; this DoneClaim records subsequent current Repair 2 verification.

## Retention Trade-Off

Linux has no conditional pathname unlink/rmdir by expected inode. Retention therefore favors safety over automatic reclamation: ambiguous stages and sidecars remain durable evidence, trading storage and possible fail-closed availability for racer preservation. Public final paths are never cleaned after publication.

## Verified Gates

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
# 200 passed in 2.41s

source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project /tmp/opencode/output-layout-pyrightconfig.json scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
# 0 errors, 0 warnings, 0 notes

source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
# exit 0

source ~/cd_vlaplan && source .venv/bin/activate && python /home/sukaih/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/dist/skills/programming/scripts/python/check-no-excuse-rules.py scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
# no violations in 35 file(s)

git diff --check
# exit 0, no output
```

Synthetic receipt lifecycle QA: `synthetic receipt lifecycle: pass`. LSP diagnostics were clean for all changed files checked.

## Scope Attestation

All fixtures are synthetic `tmp_path` or temporary-directory fixtures except the authorized read-only protected-target existence (`lstat`) test included in the full suite. No other real output contents were listed, read, hashed, written, moved, relinked, or deleted. No Todo 4 code or plan file was changed.

VERDICT: PASS
