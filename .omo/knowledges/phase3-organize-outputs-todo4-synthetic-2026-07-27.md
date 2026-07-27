# Phase 3 Todo 4 Synthetic Organizer Hardening

## Implementation map

The Task 4 organizer is coordinated by `scripts/phase3/organize_outputs.py`. Existing helpers remain `scripts/phase3/organize_outputs_receipt.py`, `scripts/phase3/organize_outputs_preflight.py`, `scripts/phase3/organize_outputs_view.py`, and `scripts/phase3/output_layout_rename.py`.

Todo 4 added these modules:

- `scripts/phase3/organize_outputs_catalog.py`
- `scripts/phase3/organize_outputs_inventory.py`
- `scripts/phase3/output_layout_writer_detection.py`
- `scripts/phase3/output_layout_writer_registry.py`

The focused synthetic surface includes `tests/phase3/organize_outputs_support.py`, `test_organize_outputs.py`, `test_organize_outputs_semantics.py`, `test_organize_outputs_adversarial.py`, `test_organize_outputs_catalog.py`, `test_organize_outputs_inventory.py`, `test_organize_outputs_hardening.py`, and `test_output_layout_writer_detection.py`.

## Reusable hardening knowledge

### Validate the live inventory at every mutation boundary

Validating only once at startup leaves resumed or long-running operations open to new unknown roots. `validate_current_output_inventory` checks that `outputs/` is an existing real directory and that each immediate child belongs to the immutable contract or the permitted `datasets` and `deprecated` roots. Apply calls it before receipt work, around each relocation, before view creation, and before marking completion. Verify calls it before receipt reading. Rejection is read-only and reports the lexicographically first unknown root.

### Separate the mutating receipt policy from read-only verification

Apply compares the supplied `Path` directly with the repository's canonical receipt path. This is deliberately lexical. A spelling containing `..` is rejected even if filesystem resolution would reach the same leaf, and rejection happens before lock entry or mutation. Verify has a different contract: it may read a complete external receipt, but receipt I/O still requires a private mode-`0600` regular file. Verification does not rewrite that external input.

### Publish catalogs as durable no-replace artifacts

Catalog stdout remains a pure serialization path. File publication opens a real parent without following symlinks, checks the destination is absent, creates an owned private temporary with `O_EXCL`, completes partial writes, fsyncs the file, and publishes with descriptor-relative `RENAME_NOREPLACE`. It then fsyncs the parent and rechecks parent identity. Existing leaves and racing publishers always win. Cleanup removes a temporary only when its device and inode still match the publisher's owned file. If `renameat2` or no-replace publication is unavailable, publication fails closed rather than falling back to replacement.

### Detect writers from exact process semantics, not command substrings

`output_layout_writer_registry.py` recognizes only approved direct script paths and exact module names. It mirrors each writer's effective mutating subcommands, parser defaults, optional update roots, dry-run exclusions, and last-option-wins behavior. This avoids both missing default writers and treating incidental text as an active writer.

`output_layout_writer_detection.py` reads NUL-framed `/proc/<pid>/cmdline`, skips its own PID, and resolves relative registered targets against `/proc/<pid>/cwd`. Equal paths, ancestors, and descendants all overlap. Absolute targets do not require a `cwd` read. A process that disappears during inspection is ignored, but malformed framing, malformed recognized arguments, unreadable live metadata, or an unresolved live `cwd` fails closed with PID-aware typed metadata.

## Latest grounded evidence

The eight focused paths ran in the required environment with:

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

Final remediated result: `81 passed in 13.29s`. Basedpyright reported `0 errors, 0 warnings, 0 notes`; compileall exited 0; the no-excuse checker reported `no violations in 11 file(s)`.

Manual synthetic CLI QA printed successful apply and external-receipt verify JSON envelopes. Assertions covered exact stdout-only catalog rendering, silent mode-`0600` catalog publication, mode-`0600` external receipt verification without rewrite, and fake-`/proc` detection of a PID-relative Planimation overlap from `python -- scripts/phase3/generate_planimation_vlm.py` as a direct script without module reinterpretation.

Final Oracle remediation review reported no blocking findings after proof of catalog temporary-substitution prevention, final inventory validation for a fresh prepared receipt, and Python `--` direct-script recognition without module reinterpretation.

`tests/phase3/test_phase3_writer_output_layout_lock.py` could not collect in required `ada_vla` Python 3.10 because its pre-existing support imports `typing.assert_never`, which is available in the standard library starting with Python 3.11. No lock implementation, lock test, product writer, or support file was changed to bypass that environment-only limitation.

All work and evidence were synthetic only. No real output tree was inspected or touched, no production migration ran, and no commit was made.
