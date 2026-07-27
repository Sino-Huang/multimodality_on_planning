# Phase 3 Output Layout Wave 1 Security Hardening

Wave 1 receipt reads must open untrusted receipt and fixed-sidecar names with
`O_NOFOLLOW | O_NONBLOCK`, validate the descriptor is a regular file before
reading, and require an exact `0600` mode for public receipts. Tests that are
intended to exercise parsing or recovery must set hand-authored receipt
fixtures to `0600`; permission-rejection tests must retain insecure modes.

Deterministic inventory snapshots and protected-content tokens use explicit
directory-depth caps in addition to entry caps. Receipt JSON limits count every
object member and array element across the complete document before typed
materialization. Duplicate-key detection remains at the JSON object-pairs
boundary.

Private-stage cleanup records the device, inode, and file type of each entry
created by the invocation. It deletes only entries whose descriptor-relative
identity remains equal, in reverse creation order. An unowned or replaced
child remains in the quarantined stage as evidence and causes cleanup to fail.

Verification recorded under
`.omo/evidence/output-layout/task-1-3-security-hardening/`:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_acceptance_security.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q .omo/evidence/output-layout/task-1-3-security-hardening/manual_filesystem_qa.py
```

Final results were 18 focused acceptance tests passed, 172 output-layout tests
passed, and the isolated FIFO/quarantine filesystem scenario passed. The QA
fixture uses only pytest `tmp_path`; no command targets a real `outputs/` path.

The command-line Basedpyright, compileall, no-excuse, pure-LOC, and
`git diff --check` results are recorded in the same evidence directory.
