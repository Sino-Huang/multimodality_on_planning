# Phase 3 Organizer Hardening and Writer Detection

## Scope

This handoff covers Todo 4 hardening for the synthetic Phase 3 output organizer. It documents inventory gates, receipt-path policy, durable catalog publication, and exact writer detection. No real output tree was inspected, moved, rewritten, or verified. No production migration ran, and no commit was made.

## Shipped implementation

The existing coordinator remains `scripts/phase3/organize_outputs.py`, backed by `organize_outputs_preflight.py`, `organize_outputs_receipt.py`, `organize_outputs_view.py`, and `output_layout_rename.py`.

Todo 4 added four modules:

- `scripts/phase3/organize_outputs_catalog.py` publishes catalog files durably without replacement.
- `scripts/phase3/organize_outputs_inventory.py` validates the current immediate `outputs/` inventory.
- `scripts/phase3/output_layout_writer_registry.py` maps exact writer invocations to their effective target roots.
- `scripts/phase3/output_layout_writer_detection.py` inspects process metadata and finds path overlaps.

## Contracts

### Inventory boundaries

Apply validates the current inventory before receipt preparation, around relocation work, before view publication, and before completion. Verify validates before it reads the receipt. `outputs/` must be a real directory. Unknown immediate children are rejected deterministically, without filesystem mutation.

### Apply and verify receipts

Apply is mutating, so it accepts only the exact lexical canonical path `outputs/deprecated/phase3/output_reorganization_20260726.json`. It does not normalize alternate spellings into acceptance. A noncanonical path fails before lock acquisition.

Verify is read-only and may use a complete receipt outside the repository. Existing receipt I/O still requires a mode-`0600` regular file and validates the sealed receipt. Successful external verification leaves the receipt bytes and mode unchanged.

### Catalog publication

Without `--output`, `catalog` prints only the exact serialized immutable catalog. With `--output`, publication is silent and uses a private mode-`0600` temporary regular file. The publisher handles short writes, fsyncs the temporary, uses descriptor-relative `RENAME_NOREPLACE`, fsyncs the parent, and checks that the opened parent was not replaced. It never overwrites an existing leaf. Unsupported no-replace publication, symlink traversal, collisions, live parent replacement, and metadata or durability failures are typed failures.

### Writer detection

Detection matches exact approved direct scripts or exact `python -m` module names. Registered behavior follows effective writer roots, defaults, mutating subcommands, optional update targets, dry-run exclusions, and last repeated option values. It does not match incidental command text.

For each live PID, absolute targets are resolved directly and relative targets are resolved against that PID's `cwd`. Equal, ancestor, and descendant paths count as overlap. The current PID is skipped. Normal process disappearance is tolerated, while malformed NUL framing, malformed recognized invocations, unreadable live command metadata, and unresolved live `cwd` fail closed with PID-aware errors.

## Required-environment verification

Run the focused synthetic suite with this copy-pastable command:

```bash
source ~/cd_vlaplan && PYTHONPATH="$PWD/tests/phase3" python -m pytest -q \
  tests/phase3/organize_outputs_support.py \
  tests/phase3/test_organize_outputs.py \
  tests/phase3/test_organize_outputs_semantics.py \
  tests/phase3/test_organize_outputs_adversarial.py \
  tests/phase3/test_organize_outputs_catalog.py \
  tests/phase3/test_organize_outputs_inventory.py \
  tests/phase3/test_organize_outputs_hardening.py \
  tests/phase3/test_output_layout_writer_detection.py
```

Final remediated result: `81 passed in 13.29s`.

Use the following commands to recheck the hardening source and focused tests in the same required environment. These are current rerun commands, not a reconstruction of an unrecorded historical command line:

```bash
source ~/cd_vlaplan && basedpyright \
  scripts/phase3/organize_outputs.py \
  scripts/phase3/organize_outputs_preflight.py \
  scripts/phase3/organize_outputs_catalog.py \
  scripts/phase3/organize_outputs_inventory.py \
  scripts/phase3/output_layout_writer_detection.py \
  scripts/phase3/output_layout_writer_registry.py \
  tests/phase3/organize_outputs_support.py \
  tests/phase3/test_organize_outputs_catalog.py \
  tests/phase3/test_organize_outputs_inventory.py \
  tests/phase3/test_organize_outputs_hardening.py \
  tests/phase3/test_output_layout_writer_detection.py

source ~/cd_vlaplan && python -m compileall -q \
  scripts/phase3/organize_outputs.py \
  scripts/phase3/organize_outputs_preflight.py \
  scripts/phase3/organize_outputs_catalog.py \
  scripts/phase3/organize_outputs_inventory.py \
  scripts/phase3/output_layout_writer_detection.py \
  scripts/phase3/output_layout_writer_registry.py \
  tests/phase3/organize_outputs_support.py \
  tests/phase3/test_organize_outputs_catalog.py \
  tests/phase3/test_organize_outputs_inventory.py \
  tests/phase3/test_organize_outputs_hardening.py \
  tests/phase3/test_output_layout_writer_detection.py

source ~/cd_vlaplan && python /home/sukaih/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/dist/skills/programming/scripts/python/check-no-excuse-rules.py \
  scripts/phase3/organize_outputs.py \
  scripts/phase3/organize_outputs_preflight.py \
  scripts/phase3/organize_outputs_catalog.py \
  scripts/phase3/organize_outputs_inventory.py \
  scripts/phase3/output_layout_writer_detection.py \
  scripts/phase3/output_layout_writer_registry.py \
  tests/phase3/organize_outputs_support.py \
  tests/phase3/test_organize_outputs_catalog.py \
  tests/phase3/test_organize_outputs_inventory.py \
  tests/phase3/test_organize_outputs_hardening.py \
  tests/phase3/test_output_layout_writer_detection.py
```

Latest grounded static results were Basedpyright `0 errors, 0 warnings, 0 notes`, compileall exit 0, and no-excuse `no violations in 11 file(s)`.

## Manual synthetic QA evidence

Manual CLI QA printed these success envelopes:

```json
{"command": "apply", "ok": true}
{"command": "verify", "ok": true}
```

The verify envelope came from a complete external mode-`0600` receipt. The QA also asserted exact catalog-only stdout when no output path was supplied, silent exact catalog publication at mode `0600`, unchanged external receipt bytes and mode after verification, and detection of a fake-`/proc` PID using `python -- scripts/phase3/generate_planimation_vlm.py` whose relative Planimation target overlapped the relocation source after resolution against that PID's `cwd`. The invocation was recognized as a direct script without module reinterpretation.

## Final Oracle review

The remediation review reported no blocking findings after proof of catalog temporary-substitution prevention, final inventory validation for a fresh prepared receipt, and Python `--` direct-script recognition without module reinterpretation.

## Residual environment limitation

This required-environment command does not collect:

```bash
source ~/cd_vlaplan && PYTHONPATH="$PWD/tests/phase3" python -m pytest -q tests/phase3/test_phase3_writer_output_layout_lock.py
```

The required `ada_vla` environment uses Python 3.10. Pre-existing support imports `typing.assert_never`, a standard-library symbol available from Python 3.11. No lock implementation, lock test, product writer, organizer source, or support file was changed to work around this environment-only collection limitation.
