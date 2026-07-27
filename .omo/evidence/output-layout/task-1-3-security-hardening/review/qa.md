# Output Layout Wave 1 Security-Hardening QA

## Scope And Safety Boundary

Independent hands-on QA covered Wave 1 output-layout Todos 1-3. No product
code or tests were changed. Every executed command began with the required
environment prefix:

```bash
source ~/cd_vlaplan && source .venv/bin/activate &&
```

No command read, wrote, listed, hashed, or otherwise inspected the real
`outputs/` tree. All executed test scenarios used pytest `tmp_path` fixtures;
the dedicated cleanup run also used an isolated
`/tmp/output-layout-security-qa-*` root.

## Commands And Results

Focused five-file pytest command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest -p no:cacheprovider -q tests/phase3/test_output_layout_acceptance_security.py tests/phase3/test_output_layout_receipt_adversarial.py tests/phase3/test_output_layout_snapshot_adversarial.py tests/phase3/test_output_layout_view_fs_adversarial.py tests/phase3/test_output_layout_view_races.py
```

Result: exit 0; `93 passed in 1.21s`.

Authoritative synthetic security QA command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp python .omo/evidence/output-layout/task-1-3-security-hardening/synthetic_authoritative_security_qa.py
```

Result: exit 0; `18 passed in 0.40s`.

Safe output-layout glob command (one real-output test explicitly deselected):

```bash
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest -p no:cacheprovider -q tests/phase3/test_output_layout_*.py -k 'not test_real_repository_has_all_fifteen_protected_view_targets'
```

Result: exit 0; `189 passed, 1 deselected in 1.59s`.

The required unqualified command below was not executed:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
```

Reason: its collected test
`test_real_repository_has_all_fifteen_protected_view_targets` calls `lstat()`
on each real protected `outputs/` target. Running it would violate the stated
no-real-`outputs/` safety boundary.

## A-F Filesystem Observables

- A: The protected-content and snapshot FIFO-substitution scenarios passed.
  Each replaces a synthetic regular file with a FIFO, asserts `O_NONBLOCK` at
  reopen, and observes a normalized rejection rather than a block.
- B: The private-stage scanner and fsync walker depth and entry-limit matrix
  passed. Synthetic trees beyond the monkeypatched limit failed with bounded
  `OSError` results.
- C: The partial-stage construction scenario passed. It retained the injected
  `racer-owned` file under the synthetic `.cleanup` quarantine and preserved
  the primary `synthetic construction failure` as the cause.
- D: Both quarantine revalidation scenarios passed. The stage replacement was
  retained as the synthetic quarantine directory, and the receipt replacement
  remained at `.receipt.json.txn.remove` with the injected racer bytes.
- E: The post-publish final-name racer scenario passed. It left no synthetic
  public view root and retained the injected racer directory at the final
  name, demonstrating that cleanup did not delete the replacement.
- F: All eight recovery-sidecar mode matrix cases passed. Only exact `0600`
  completed recovery and removed the synthetic sidecars; `0644`, `0660`, and
  `0604` were rejected with the mode-`0600` error.

## Cleanup Receipt

An isolated rerun used this exact command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && qa_tmp=$(mktemp -d /tmp/output-layout-security-qa-XXXXXX) && PYTHONDONTWRITEBYTECODE=1 TMPDIR="$qa_tmp" python .omo/evidence/output-layout/task-1-3-security-hardening/synthetic_authoritative_security_qa.py && rm -rf "$qa_tmp" && test ! -e "$qa_tmp" && print 'cleanup receipt: removed synthetic temporary root'
```

Result: exit 0; `18 passed in 0.48s`; emitted
`cleanup receipt: removed synthetic temporary root`. The removed directory was
created by this command under `/tmp`; no repository output path was involved.

## Residual Gaps

The full unqualified `tests/phase3/test_output_layout_*.py` command remains
unverified because it includes an explicitly real-output-reading test. The
synthetic-only alternative passed 189 tests with that one test deselected.
This is a compliance gap against the requested full-suite command, not a
synthetic test failure.

VERDICT: FAIL
